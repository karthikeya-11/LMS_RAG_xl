"""
Teams Bot with SSO-Only Authentication
Frontend bot that uses Microsoft SSO for authentication.
Backend verification is handled by teamssdk/ modules.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass

from dotenv import load_dotenv
import aiohttp
from botbuilder.core import (
    ActivityHandler, MessageFactory, TurnContext,
    BotFrameworkAdapter, BotFrameworkAdapterSettings, CardFactory
)
from botbuilder.schema import (
    Activity, ActivityTypes, ChannelAccount, Attachment,
    OAuthCard, CardAction, ActionTypes
)
from aiohttp import web
from aiohttp.web import Request, Response

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# --- Configuration ---
class Config:
    """Application configuration"""
    BOT_PORT = int(os.getenv("BOT_PORT", 3978))
    MICROSOFT_APP_ID = os.getenv("MICROSOFT_APP_ID", "")
    MICROSOFT_APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")
    MICROSOFT_APP_TENANT_ID = os.getenv("MICROSOFT_APP_TENANT_ID", "")
    
    # OAuth connection name configured in Azure Bot
    OAUTH_CONNECTION_NAME = os.getenv("OAUTH_CONNECTION_NAME", "AADConnection")
    
    # Backend API endpoints (Flask local server)
    API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5001")
    SSO_VERIFY_ENDPOINT = f"{API_BASE_URL}/api/verify-sso"
    CHAT_API_ENDPOINT = f"{API_BASE_URL}/api/chat"
    
    # Session timeout
    SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", 60))


@dataclass
class SessionData:
    """User session data"""
    auth_token: str
    last_activity: datetime
    employee_name: str = ""
    email: str = ""


class SSOCardFactory:
    """Factory for creating SSO authentication cards"""
    
    @staticmethod
    def create_welcome_card() -> Attachment:
        """Welcome card with SSO sign-in button"""
        card_content = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "🏢 tech.at.core Leave Management",
                    "weight": "bolder",
                    "size": "large",
                    "horizontalAlignment": "center"
                },
                {
                    "type": "TextBlock",
                    "text": "Welcome! Please sign in with your Microsoft account to continue.",
                    "wrap": True,
                    "spacing": "medium",
                    "horizontalAlignment": "center"
                },
                {
                    "type": "TextBlock",
                    "text": "🔒 Secure Single Sign-On (SSO) Authentication",
                    "wrap": True,
                    "size": "small",
                    "isSubtle": True,
                    "horizontalAlignment": "center"
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "🔐 Sign in with Microsoft",
                    "data": {"action": "sso_login"},
                    "style": "positive"
                }
            ]
        }
        
        return Attachment(
            content_type="application/vnd.microsoft.card.adaptive",
            content=card_content
        )
    
    @staticmethod
    def create_success_card(employee_name: str) -> Attachment:
        """Success card after authentication"""
        card_content = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "✅ Successfully Signed In",
                    "weight": "bolder",
                    "size": "large",
                    "color": "good",
                    "horizontalAlignment": "center"
                },
                {
                    "type": "TextBlock",
                    "text": f"Welcome, **{employee_name}**!",
                    "wrap": True,
                    "spacing": "medium",
                    "horizontalAlignment": "center",
                    "size": "medium"
                },
                {
                    "type": "TextBlock",
                    "text": "You can now manage your leave requests. Try asking:",
                    "wrap": True,
                    "spacing": "medium"
                },
                {
                    "type": "TextBlock",
                    "text": "• What is my leave balance?\n• I need leave\n• Show my leave history\n• Help",
                    "wrap": True,
                    "spacing": "small"
                }
            ]
        }
        
        return Attachment(
            content_type="application/vnd.microsoft.card.adaptive",
            content=card_content
        )
    
    @staticmethod
    def create_error_card(error_message: str) -> Attachment:
        """Error card for authentication failures"""
        card_content = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "❌ Authentication Failed",
                    "weight": "bolder",
                    "size": "large",
                    "color": "attention",
                    "horizontalAlignment": "center"
                },
                {
                    "type": "TextBlock",
                    "text": error_message,
                    "wrap": True,
                    "spacing": "medium",
                    "horizontalAlignment": "center"
                },
                {
                    "type": "TextBlock",
                    "text": "Possible reasons:\n• Email not found in employee database\n• Invalid Microsoft token\n• Network connection issue",
                    "wrap": True,
                    "size": "small",
                    "isSubtle": True,
                    "spacing": "medium"
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "🔄 Try Again",
                    "data": {"action": "retry_login"}
                }
            ]
        }
        
        return Attachment(
            content_type="application/vnd.microsoft.card.adaptive",
            content=card_content
        )


class LeaveManagementSSOBot(ActivityHandler):
    """Teams bot with SSO-only authentication"""
    
    def __init__(self):
        super().__init__()
        self.active_sessions: Dict[str, SessionData] = {}
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        logger.info("🤖 LeaveManagementSSOBot initialized")
        logger.info(f"   OAuth Connection: {Config.OAUTH_CONNECTION_NAME}")
        logger.info(f"   SSO Verification: {Config.SSO_VERIFY_ENDPOINT}")
        logger.info(f"   Session Timeout: {Config.SESSION_TIMEOUT_MINUTES} minutes")
    
    async def on_turn(self, turn_context: TurnContext):
        """Main turn handler"""
        try:
            # Create HTTP session if needed
            if not self.http_session:
                self.http_session = aiohttp.ClientSession()
            
            await super().on_turn(turn_context)
            
        except Exception as e:
            logger.error(f"❌ Error in on_turn: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text("An unexpected error occurred. Please try again.")
            )
    
    async def on_message_activity(self, turn_context: TurnContext):
        """Handle incoming messages"""
        user_id = turn_context.activity.from_property.id
        text = turn_context.activity.text.strip() if turn_context.activity.text else ""
        
        logger.info(f"📨 Message from {user_id}: {text[:50]}...")
        
        # Check for adaptive card submit (button clicks)
        if turn_context.activity.value:
            await self._handle_card_action(turn_context)
            return
        
        # Check if user has valid session
        session_data = self._get_valid_session(user_id)
        
        if not session_data:
            logger.info("   No valid session, prompting for SSO login")
            await turn_context.send_activity(
                MessageFactory.text("Please sign in to continue.")
            )
            await turn_context.send_activity(
                MessageFactory.attachment(SSOCardFactory.create_welcome_card())
            )
            return
        
        # Handle logout
        if text.lower() in ["logout", "exit", "quit", "sign out"]:
            await self._handle_logout(turn_context, user_id)
            return
        
        # Process authenticated message
        await self._process_authenticated_message(turn_context, user_id, text, session_data)
    
    def _get_valid_session(self, user_id: str) -> Optional[SessionData]:
        """Get valid session or None if expired"""
        session = self.active_sessions.get(user_id)
        if not session:
            return None
        
        # Check timeout
        time_elapsed = datetime.utcnow() - session.last_activity
        if time_elapsed > timedelta(minutes=Config.SESSION_TIMEOUT_MINUTES):
            logger.info(f"Session expired for {user_id}")
            del self.active_sessions[user_id]
            return None
        
        # Update last activity
        session.last_activity = datetime.utcnow()
        return session
    
    async def _handle_card_action(self, turn_context: TurnContext):
        """Handle adaptive card button clicks"""
        data = turn_context.activity.value
        action = data.get("action") if data else None
        
        logger.info(f"🎯 Card action: {action}")
        
        if action == "sso_login":
            await self._initiate_sso(turn_context)
        elif action == "retry_login":
            await turn_context.send_activity(
                MessageFactory.attachment(SSOCardFactory.create_welcome_card())
            )
        else:
            logger.warning(f"Unknown action: {action}")
            await turn_context.send_activity(
                MessageFactory.text("Unknown action. Please try again.")
            )
    
    async def _initiate_sso(self, turn_context: TurnContext):
        """Initiate SSO sign-in flow"""
        user_id = turn_context.activity.from_property.id
        logger.info(f"🔐 Initiating SSO for user: {user_id}")
        
        try:
            adapter = turn_context.adapter
            
            # Check if adapter supports OAuth
            if not hasattr(adapter, 'get_sign_in_resource_from_user'):
                logger.error("❌ Adapter does not support OAuth")
                await turn_context.send_activity(
                    MessageFactory.attachment(
                        SSOCardFactory.create_error_card(
                            "SSO is not properly configured. Please contact support."
                        )
                    )
                )
                return
            
            # Get sign-in resource
            logger.info(f"   Requesting sign-in resource with connection: {Config.OAUTH_CONNECTION_NAME}")
            sign_in_resource = await adapter.get_sign_in_resource_from_user(
                turn_context,
                Config.OAUTH_CONNECTION_NAME,
                user_id
            )
            
            if not sign_in_resource:
                logger.error("❌ Failed to get sign-in resource")
                await turn_context.send_activity(
                    MessageFactory.attachment(
                        SSOCardFactory.create_error_card(
                            "Unable to initiate sign-in. Please check OAuth connection configuration."
                        )
                    )
                )
                return
            
            logger.info(f"   ✓ Got sign-in link: {sign_in_resource.sign_in_link}")
            
            # Create and send OAuth card
            oauth_card = OAuthCard(
                text="Please sign in with your Microsoft account",
                connection_name=Config.OAUTH_CONNECTION_NAME,
                buttons=[
                    CardAction(
                        type=ActionTypes.signin,
                        title="Sign In",
                        value=sign_in_resource.sign_in_link
                    )
                ]
            )
            
            oauth_card_attachment = CardFactory.oauth_card(oauth_card)
            await turn_context.send_activity(
                MessageFactory.attachment(oauth_card_attachment)
            )
            
            logger.info("   ✅ OAuth card sent successfully")
            
        except Exception as e:
            logger.error(f"❌ SSO initiation failed: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.attachment(
                    SSOCardFactory.create_error_card(
                        f"SSO initiation failed: {str(e)}"
                    )
                )
            )
    
    async def _handle_logout(self, turn_context: TurnContext, user_id: str):
        """Handle user logout"""
        if user_id in self.active_sessions:
            del self.active_sessions[user_id]
            logger.info(f"👋 User {user_id} logged out")
        
        await turn_context.send_activity(
            MessageFactory.text("👋 You have been logged out successfully. See you next time!")
        )
        await turn_context.send_activity(
            MessageFactory.attachment(SSOCardFactory.create_welcome_card())
        )
    
    async def _process_authenticated_message(
        self, 
        turn_context: TurnContext, 
        user_id: str, 
        text: str, 
        session_data: SessionData
    ):
        """Process message from authenticated user"""
        logger.info(f"💬 Processing message from {session_data.employee_name}")
        
        try:
            # Send typing indicator
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))
            
            # Call backend chat API
            headers = {"Authorization": f"Bearer {session_data.auth_token}"}
            payload = {"message": text}
            
            async with self.http_session.post(
                Config.CHAT_API_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=30
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract response text
                    response_text = data.get("response")
                    if not response_text:
                        # Fallback: get from history
                        history = data.get("full_history", [])
                        if history:
                            for msg in reversed(history):
                                if msg.get("type") == "ai" and msg.get("content"):
                                    response_text = msg["content"]
                                    break
                    
                    if response_text:
                        await turn_context.send_activity(MessageFactory.text(response_text))
                    else:
                        logger.error(f"No valid response in API return: {data}")
                        await turn_context.send_activity(
                            MessageFactory.text("Sorry, I received an invalid response from the server.")
                        )
                
                elif response.status in [401, 403]:
                    # Session expired on backend
                    logger.warning(f"Backend auth failed: {response.status}")
                    del self.active_sessions[user_id]
                    
                    await turn_context.send_activity(
                        MessageFactory.text("Your session has expired. Please sign in again.")
                    )
                    await turn_context.send_activity(
                        MessageFactory.attachment(SSOCardFactory.create_welcome_card())
                    )
                
                else:
                    error_data = await response.json()
                    error_msg = error_data.get("error", "Failed to process request")
                    logger.error(f"Chat API error {response.status}: {error_msg}")
                    await turn_context.send_activity(
                        MessageFactory.text(f"Error: {error_msg}")
                    )
        
        except asyncio.TimeoutError:
            logger.error("Chat API request timed out")
            await turn_context.send_activity(
                MessageFactory.text("Request timed out. Please try again.")
            )
        
        except Exception as e:
            logger.error(f"Chat API error: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text("Sorry, I'm having trouble connecting to the service. Please try again later.")
            )
    
    async def on_members_added_activity(
        self, 
        members_added: list, 
        turn_context: TurnContext
    ):
        """Handle new members added to conversation"""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                logger.info(f"👋 New member: {member.id}")
                
                welcome_text = (
                    "👋 **Welcome to the tech.at.core Leave Management Bot!**\n\n"
                    "I can help you:\n"
                    "• Apply for leave\n"
                    "• Check leave balance\n"
                    "• View leave history\n"
                    "• And more!\n\n"
                    "Please sign in to get started."
                )
                
                await turn_context.send_activity(MessageFactory.text(welcome_text))
                await turn_context.send_activity(
                    MessageFactory.attachment(SSOCardFactory.create_welcome_card())
                )
    
    async def on_invoke_activity(self, turn_context: TurnContext):
        """Handle invoke activities (for SSO token exchange)"""
        logger.info(f"📞 Invoke activity: {turn_context.activity.name}")
        
        if turn_context.activity.name == "signin/tokenExchange":
            await self._handle_token_exchange(turn_context)
        elif turn_context.activity.name == "signin/verifyState":
            await self._handle_verify_state(turn_context)
        else:
            logger.warning(f"Unknown invoke activity: {turn_context.activity.name}")
            await super().on_invoke_activity(turn_context)
    
    async def _handle_token_exchange(self, turn_context: TurnContext):
        """Handle SSO token exchange"""
        user_id = turn_context.activity.from_property.id
        logger.info(f"🔄 Token exchange for user: {user_id}")
        
        try:
            # Extract Microsoft token from activity
            if not turn_context.activity.value or 'token' not in turn_context.activity.value:
                logger.warning("❌ No token in activity value")
                await turn_context.send_activity(
                    Activity(
                        type=ActivityTypes.invoke_response,
                        value={"status": 412, "body": {"error": "Token missing"}}
                    )
                )
                return
            
            ms_token = turn_context.activity.value['token']
            logger.info("✅ Microsoft token received via exchange")
            
            # Verify token with backend API
            async with self.http_session.post(
                Config.SSO_VERIFY_ENDPOINT,
                json={"access_token": ms_token},
                timeout=10
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Create session with internal JWT token from backend
                    self.active_sessions[user_id] = SessionData(
                        auth_token=data.get("token"),
                        last_activity=datetime.utcnow(),
                        employee_name=data.get("employee_name", "User"),
                        email=data.get("email", "")
                    )
                    
                    logger.info(f"✅ SSO authentication successful for: {data.get('employee_name')}")
                    
                    # Send success response to Teams
                    await turn_context.send_activity(
                        Activity(
                            type=ActivityTypes.invoke_response,
                            value={"status": 200, "body": {"status": "success"}}
                        )
                    )
                    
                    # Send welcome card
                    await turn_context.send_activity(
                        MessageFactory.attachment(
                            SSOCardFactory.create_success_card(data.get("employee_name", "User"))
                        )
                    )
                
                else:
                    # Backend verification failed
                    error_data = await response.json()
                    error_msg = error_data.get("error", "Authentication failed")
                    logger.error(f"❌ Backend verification failed: {error_msg}")
                    
                    await turn_context.send_activity(
                        Activity(
                            type=ActivityTypes.invoke_response,
                            value={"status": 401, "body": {"error": error_msg}}
                        )
                    )
                    
                    await turn_context.send_activity(
                        MessageFactory.attachment(
                            SSOCardFactory.create_error_card(error_msg)
                        )
                    )
        
        except asyncio.TimeoutError:
            logger.error("❌ Token verification timeout")
            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.invoke_response,
                    value={"status": 500, "body": {"error": "Verification timeout"}}
                )
            )
        
        except Exception as e:
            logger.error(f"❌ Token exchange error: {e}", exc_info=True)
            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.invoke_response,
                    value={"status": 500, "body": {"error": str(e)}}
                )
            )
    
    async def _handle_verify_state(self, turn_context: TurnContext):
        """Handle verify state activity"""
        logger.info("🔍 Verify state activity")
        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.invoke_response,
                value={"status": 200}
            )
        )
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.http_session:
            await self.http_session.close()
            logger.info("HTTP session closed")


# --- Application Setup ---
# For local testing without authentication, leave app_id and app_password empty
# For production, set MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD in .env
SETTINGS = BotFrameworkAdapterSettings(
    app_id=Config.MICROSOFT_APP_ID,
    app_password=Config.MICROSOFT_APP_PASSWORD
)
ADAPTER = BotFrameworkAdapter(SETTINGS)
BOT = LeaveManagementSSOBot()

logger.info(f"Bot adapter configured:")
logger.info(f"  App ID: {'(empty - local mode)' if not Config.MICROSOFT_APP_ID else Config.MICROSOFT_APP_ID}")
logger.info(f"  Authentication: {'Disabled (local testing)' if not Config.MICROSOFT_APP_ID else 'Enabled (production)'}")


async def on_error(context: TurnContext, error: Exception):
    """Global error handler"""
    logger.error(f"❌ Error in turn handler: {error}", exc_info=True)
    await context.send_activity(
        MessageFactory.text("The bot encountered an error. Please try again.")
    )


ADAPTER.on_turn_error = on_error


# --- Web Server ---
async def messages(req: Request) -> Response:
    """Handle incoming bot messages"""
    if "application/json" not in req.headers.get("Content-Type", ""):
        return Response(status=415, text="Unsupported Media Type")
    
    try:
        body = await req.json()
        activity = Activity().deserialize(body)
        auth_header = req.headers.get("Authorization", "")
        
        await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
        return Response(status=200)
    
    except Exception as e:
        logger.error(f"❌ Error processing activity: {e}", exc_info=True)
        return Response(status=500, text=str(e))


async def health_check(req: Request) -> Response:
    """Health check endpoint"""
    return Response(
        status=200,
        text="OK - SSO Bot Running",
        content_type="text/plain"
    )


def create_app():
    """Create aiohttp web application"""
    app = web.Application()
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", health_check)
    return app


async def main():
    """Main application entry point"""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', Config.BOT_PORT)
    await site.start()
    
    logger.info("=" * 70)
    logger.info("🚀 TEAMS BOT WITH SSO AUTHENTICATION STARTED")
    logger.info("=" * 70)
    logger.info(f"   Bot listening on: http://localhost:{Config.BOT_PORT}/api/messages")
    logger.info(f"   Health check: http://localhost:{Config.BOT_PORT}/health")
    logger.info(f"   App ID: {Config.MICROSOFT_APP_ID if Config.MICROSOFT_APP_ID else 'Not configured'}")
    logger.info(f"   OAuth Connection: {Config.OAUTH_CONNECTION_NAME}")
    logger.info(f"   Backend API: {Config.API_BASE_URL}")
    logger.info(f"   SSO Verification: {Config.SSO_VERIFY_ENDPOINT}")
    logger.info(f"   Authentication Mode: SSO ONLY (Password login removed)")
    logger.info("=" * 70)
    
    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped manually")
    except Exception as e:
        logger.critical(f"❌ Application failed to start: {e}", exc_info=True)
    finally:
        # Cleanup
        if BOT.http_session:
            asyncio.run(BOT.cleanup())
