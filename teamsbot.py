# teams_bot.py - Microsoft Teams Bot integrated with your Leave Management System
#--------------------------------------------------------------------------------------------------------

# teams_bot.py - Microsoft Teams Bot integrated with your Leave Management System

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Bot Framework imports
from botbuilder.core import (
    ActivityHandler, MessageFactory, TurnContext, CardFactory,
    ConversationState, UserState, MemoryStorage, BotFrameworkAdapter,
    BotFrameworkAdapterSettings
)
from botbuilder.schema import Activity, ActivityTypes, ChannelAccount, Attachment
from aiohttp import web
from aiohttp.web import Request, Response

# Your existing imports
USE_DIRECT_AGENT = os.getenv("USE_DIRECT_AGENT", "false").lower() == "true"

if USE_DIRECT_AGENT:
    from agent.agent_graph import get_graph_app
    from services import excel_handler  # only needed for direct path
    from api.auth import create_token
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
else:
    # Decoupled mode uses HTTP backend
    from services import excel_handler  # still used for local credential verify if we keep login local? We'll defer to backend.
    from services import backend_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if USE_DIRECT_AGENT:
    # --- Agent and Graph Initialization (Direct Mode) ---
    memory = MemorySaver()
    app_builder = get_graph_app()
    graph = app_builder.compile(checkpointer=memory)
else:
    graph = None  # placeholder; backend maintains state

# Configuration
class Config:
    BOT_PORT = int(os.getenv("BOT_PORT", "3978"))

@dataclass
class SessionData:
    """Store session data for each user conversation"""
    employee_id: str
    auth_token: Optional[str]
    last_activity: datetime

class AdaptiveCardFactory:
    """Factory for creating Teams adaptive cards"""

    @staticmethod
    def create_response_card(response_text: str, conversation_state: Dict[str, Any]) -> Attachment:
        """Create adaptive card for agent responses"""
        color = "Default"
        if "Success" in response_text or "approved" in response_text.lower():
            color = "Good"
        elif "Error" in response_text or "denied" in response_text.lower() or "violation" in response_text.lower():
            color = "Attention"
        elif "pending" in response_text.lower() or "confirm" in response_text.lower():
            color = "Warning"

        body = [
            {"type": "TextBlock", "text": "🤖 HR Assistant Response", "weight": "Bolder", "size": "Large", "color": color},
            {"type": "TextBlock", "text": response_text, "wrap": True, "size": "Medium"}
        ]

        current_flow = conversation_state.get("current_flow")
        if current_flow and current_flow != 'END':
            body.append({"type": "TextBlock", "text": f"💬 Conversation: {current_flow.replace('_', ' ').title()}", "wrap": True, "size": "Small", "color": "Accent"})

        gathered_details = conversation_state.get("gathered_details", {})
        if gathered_details:
            facts = [{"title": key.replace('_', ' ').title() + ":", "value": str(value)} for key, value in gathered_details.items()]
            if facts:
                body.append({"type": "FactSet", "facts": facts})

        actions = AdaptiveCardFactory._get_contextual_actions(conversation_state)
        
        card_data = {"type": "AdaptiveCard", "version": "1.3", "body": body}
        if actions:
            card_data["actions"] = actions
        
        return CardFactory.adaptive_card(card_data)

    @staticmethod
    def _get_contextual_actions(conversation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get contextual action buttons based on conversation state"""
        if conversation_state.get("confirmation_pending", False):
            return [
                {"type": "Action.Submit", "title": "✅ Yes, Confirm", "data": {"action": "confirm_details"}, "style": "positive"},
                {"type": "Action.Submit", "title": "❌ No, Cancel", "data": {"action": "cancel_request"}}
            ]
        
        # Default actions
        return [
            {"type": "Action.Submit", "title": "📝 New Request", "data": {"action": "new_leave_request"}},
            {"type": "Action.Submit", "title": "📊 Check Balance", "data": {"action": "check_balance"}},
            {"type": "Action.Submit", "title": "📋 View History", "data": {"action": "view_history"}},
            {"type": "Action.Submit", "title": "❓ Help", "data": {"action": "help"}}
        ]

    @staticmethod
    def create_login_card() -> Attachment:
        """Create login card for authentication"""
        card_data = {
            "type": "AdaptiveCard", "version": "1.3",
            "body": [
                {"type": "TextBlock", "text": "🔐 Login Required", "weight": "Bolder", "size": "Large", "color": "Accent"},
                {"type": "TextBlock", "text": "Please log in to access the leave management system:", "wrap": True},
                {"type": "Input.Text", "id": "employeeId", "label": "Employee ID", "placeholder": "Enter your employee ID"},
                {"type": "Input.Text", "id": "password", "label": "Password", "style": "Password", "placeholder": "Enter your password"}
            ],
            "actions": [{"type": "Action.Submit", "title": "🚀 Login", "data": {"action": "login"}, "style": "positive"}]
        }
        return CardFactory.adaptive_card(card_data)

class LeaveManagementTeamsBot(ActivityHandler):
    """Microsoft Teams bot for leave management"""
    
    def __init__(self, conversation_state: ConversationState, user_state: UserState):
        self.conversation_state = conversation_state
        self.user_state = user_state
        self.active_sessions: Dict[str, SessionData] = {}
    
    async def on_turn(self, turn_context: TurnContext):
        """Override the default on_turn to handle all incoming activities."""
        await super().on_turn(turn_context)
        # Save any state changes after the turn has been processed
        await self.conversation_state.save_changes(turn_context, False)
        await self.user_state.save_changes(turn_context, False)

    async def on_message_activity(self, turn_context: TurnContext):
        try:
            user_id = turn_context.activity.from_property.id
            session_data = self.active_sessions.get(user_id)
            
            if turn_context.activity.value:
                await self._handle_adaptive_card_submit(turn_context, user_id, session_data)
                return
            
            if not session_data or not session_data.auth_token:
                await self._handle_unauthenticated_user(turn_context)
                return
            
            user_message = turn_context.activity.text.strip()
            await self._send_typing_indicator(turn_context)
            
            result = await self._process_with_agent_graph(user_id, user_message, session_data)
            
            if result.get("success"):
                response_card = AdaptiveCardFactory.create_response_card(result["response"], result.get("conversation_state", {}))
                session_data.last_activity = datetime.now()
                await turn_context.send_activity(MessageFactory.attachment(response_card))
            else:
                await turn_context.send_activity(MessageFactory.text(f"❌ {result.get('error', 'An error occurred.')}"))
            
        except Exception as e:
            logger.error(f"Error in on_message_activity: {str(e)}", exc_info=True)
            await turn_context.send_activity(MessageFactory.text("I encountered an error. Please try again or contact support."))
    
    async def _handle_adaptive_card_submit(self, turn_context: TurnContext, user_id: str, session_data: Optional[SessionData]):
        card_data = turn_context.activity.value
        action = card_data.get('action')
        
        if action == 'login':
            await self._handle_login(turn_context, user_id, card_data)
        elif not session_data or not session_data.auth_token:
            await self._handle_unauthenticated_user(turn_context)
        elif action in ['confirm_details', 'cancel_request', 'new_leave_request', 'check_balance', 'view_history', 'help']:
            await self._handle_action_buttons(turn_context, user_id, action, session_data)
    
    async def _handle_login(self, turn_context: TurnContext, user_id: str, card_data: Dict):
        employee_id = card_data.get('employeeId', '').strip()
        password = card_data.get('password', '').strip()
        
        if not employee_id or not password:
            await turn_context.send_activity(MessageFactory.text("❌ Please provide both Employee ID and Password."))
            return
        
        try:
            if USE_DIRECT_AGENT:
                # Local credential verification & token creation
                if excel_handler.verify_credentials(employee_id, password):
                    token = create_token(employee_id)
                    employee_info = excel_handler.get_employee_data(employee_id)
                    employee_name = employee_info.get('name', 'Employee') if employee_info else 'Employee'
                else:
                    await turn_context.send_activity(MessageFactory.text("❌ Invalid credentials. Please try again."))
                    return
            else:
                # Delegate login to backend
                login_resp = backend_client.login(employee_id, password)
                token = login_resp["token"]
                employee_name = login_resp.get("employee_name", "Employee")

            self.active_sessions[user_id] = SessionData(employee_id=employee_id, auth_token=token, last_activity=datetime.now())
            welcome_message = f"✅ **Welcome, {employee_name}!**\n\nYou're now logged in. How can I help you today?"
            response_card = AdaptiveCardFactory.create_response_card(welcome_message, {"current_flow": "initial"})
            await turn_context.send_activity(MessageFactory.attachment(response_card))
        except Exception as e:
            logging.error(f"Login failed: {e}")
            await turn_context.send_activity(MessageFactory.text(f"❌ Login failed: {e}"))
    
    async def _handle_action_buttons(self, turn_context: TurnContext, user_id: str, action: str, session_data: SessionData):
        action_messages = {
            'new_leave_request': 'I want to apply for leave',
            'confirm_details': 'yes',
            'cancel_request': 'no, cancel',
            'check_balance': 'What is my current leave balance?',
            'view_history': 'Show me my leave history',
            'help': 'help'
        }
        message = action_messages.get(action)

        if not message:
            await turn_context.send_activity(MessageFactory.text(f"Action '{action}' is not recognized."))
            return
        
        await self._send_typing_indicator(turn_context)
        result = await self._process_with_agent_graph(user_id, message, session_data)

        if result.get("success"):
            response_card = AdaptiveCardFactory.create_response_card(result["response"], result.get("conversation_state", {}))
            session_data.last_activity = datetime.now()
            await turn_context.send_activity(MessageFactory.attachment(response_card))
        else:
            await turn_context.send_activity(MessageFactory.text(f"❌ {result.get('error', 'Failed to process your request.')}"))

    async def _process_with_agent_graph(self, user_id: str, message: str, session_data: SessionData) -> Dict[str, Any]:
        """Process message—either locally (direct) or via backend API (decoupled)."""
        try:
            if USE_DIRECT_AGENT:
                from langchain_core.messages import HumanMessage  # local import to avoid unused when decoupled
                config = {"configurable": {"thread_id": session_data.employee_id}}
                graph_input = {"messages": [HumanMessage(content=message)]}
                final_state = None
                for chunk in graph.stream(graph_input, config, stream_mode="values"):
                    final_state = chunk
                if final_state and final_state.get("messages"):
                    response_content = final_state["messages"][-1].content
                else:
                    response_content = "Sorry, I couldn't get a response. Please try again."
                    final_state = {}
                gathered_details = {
                    "Leave Type": final_state.get("leave_type"),
                    "Start Date": final_state.get("start_date"),
                    "End Date": final_state.get("end_date"),
                }
                conversation_state_details = {
                    "current_flow": final_state.get("next_node", "END"),
                    "confirmation_pending": final_state.get("next_node") == "leave_submit",
                    "gathered_details": {k: v for k, v in gathered_details.items() if v}
                }
                return {"response": response_content, "conversation_state": conversation_state_details, "success": True}
            else:
                # Decoupled mode -> backend call
                from services.backend_client import chat, BackendAPIError
                api_result = chat(session_data.auth_token, message)
                raw = api_result["raw"]
                gathered_details = {
                    "Leave Type": raw.get("leave_type"),
                    "Start Date": raw.get("start_date"),
                    "End Date": raw.get("end_date"),
                }
                conversation_state_details = {
                    "current_flow": raw.get("next_node", "END") or "END",
                    "confirmation_pending": raw.get("next_node") == "leave_submit",
                    "gathered_details": {k: v for k, v in gathered_details.items() if v}
                }
                return {"response": api_result["response_text"], "conversation_state": conversation_state_details, "success": True}
        except Exception as e:
            err_msg = str(e)
            if "unauthorized" in err_msg.lower():
                # Force re-login
                if user_id in self.active_sessions:
                    del self.active_sessions[user_id]
                return {"success": False, "error": "Session expired. Please log in again."}
            logger.error(f"Error processing message for user {session_data.employee_id}: {e}", exc_info=True)
            return {"success": False, "error": "Internal processing error."}
    
    async def _handle_unauthenticated_user(self, turn_context: TurnContext):
        login_card = AdaptiveCardFactory.create_login_card()
        await turn_context.send_activity(MessageFactory.attachment(login_card))
    
    async def _send_typing_indicator(self, turn_context: TurnContext):
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))
    
    async def on_members_added_activity(self, members_added: List[ChannelAccount], turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(MessageFactory.text("👋 **Welcome to the HR Assistant Bot!**"))
                await self._handle_unauthenticated_user(turn_context)


# --- Application Setup ---

# Create the settings for the adapter.
# In production, get these from a secure source like Azure Key Vault.
SETTINGS = BotFrameworkAdapterSettings(
    app_id=os.getenv("MICROSOFT_APP_ID", ""),
    app_password=os.getenv("MICROSOFT_APP_PASSWORD", "")
)

# Create the BotFrameworkAdapter.
ADAPTER = BotFrameworkAdapter(SETTINGS)

# Create the main bot logic object.
BOT = LeaveManagementTeamsBot(ConversationState(MemoryStorage()), UserState(MemoryStorage()))

# --- Request Handler ---
async def messages(req: Request) -> Response:
    """Main endpoint for handling incoming bot messages."""
    if "application/json" not in req.headers.get("Content-Type", ""):
        return Response(status=415)

    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    try:
        # The adapter's process_activity method handles authentication
        # and creates the TurnContext for you.
        await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
        return Response(status=200)
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        return Response(status=500, text=str(e))

def create_app():
    """Create the aiohttp web application."""
    app = web.Application()
    app.router.add_post("/api/messages", messages)
    return app

# --- Main Execution ---
async def main():
    """Main application entry point"""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', Config.BOT_PORT)
    await site.start()
    logger.info(f"Teams Bot is listening on http://localhost:{Config.BOT_PORT}/api/messages")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")















































#========================================================================
# import asyncio
# import logging
# import os
# import sys
# from datetime import datetime
# from typing import Dict, List, Optional, Any
# from dataclasses import dataclass

# from dotenv import load_dotenv

# load_dotenv()

# # Add project root to sys.path
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# # Bot Framework imports
# from botbuilder.core import (
#     ActivityHandler, MessageFactory, TurnContext, CardFactory,
#     ConversationState, UserState, MemoryStorage, BotFrameworkAdapter,
#     BotFrameworkAdapterSettings
# )
# from botbuilder.schema import Activity, ActivityTypes, ChannelAccount, Attachment
# from aiohttp import web
# from aiohttp.web import Request, Response

# # Your existing imports
# from agent.agent_graph import get_graph_app
# from services import excel_handler
# from api.auth import create_token
# from langchain_core.messages import HumanMessage

# # LangGraph and State Management
# from langgraph.checkpoint.memory import MemorySaver

# # Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # --- Agent and Graph Initialization ---
# memory = MemorySaver()
# app_builder = get_graph_app()
# graph = app_builder.compile(checkpointer=memory)

# # Configuration
# class Config:
#     BOT_PORT = int(os.getenv("BOT_PORT", "3978"))

# @dataclass
# class SessionData:
#     """Store session data for each user conversation"""
#     employee_id: str
#     auth_token: Optional[str]
#     last_activity: datetime

# class AdaptiveCardFactory:
#     """Factory for creating Teams adaptive cards"""

#     @staticmethod
#     def create_response_card(response_text: str, conversation_state: Dict[str, Any]) -> Attachment:
#         color = "Default"
#         if "Success" in response_text or "approved" in response_text.lower():
#             color = "Good"
#         elif "Error" in response_text or "denied" in response_text.lower() or "violation" in response_text.lower():
#             color = "Attention"
#         elif "pending" in response_text.lower() or "confirm" in response_text.lower():
#             color = "Warning"

#         body = [
#             {"type": "TextBlock", "text": "🤖 HR Assistant Response", "weight": "Bolder", "size": "Large", "color": color},
#             {"type": "TextBlock", "text": response_text, "wrap": True, "size": "Medium"}
#         ]
#         current_flow = conversation_state.get("current_flow")
#         if current_flow and current_flow != 'END':
#             body.append({"type": "TextBlock", "text": f"💬 Conversation: {current_flow.replace('_', ' ').title()}", "wrap": True, "size": "Small", "color": "Accent"})
#         gathered_details = conversation_state.get("gathered_details", {})
#         if gathered_details:
#             facts = [{"title": key.replace('_', ' ').title() + ":", "value": str(value)} for key, value in gathered_details.items() if value]
#             if facts:
#                 body.append({"type": "FactSet", "facts": facts})
#         actions = AdaptiveCardFactory._get_contextual_actions(conversation_state)
#         card_data = {"type": "AdaptiveCard", "version": "1.3", "body": body}
#         if actions:
#             card_data["actions"] = actions
#         return CardFactory.adaptive_card(card_data)

#     @staticmethod
#     def _get_contextual_actions(conversation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
#         if conversation_state.get("confirmation_pending", False):
#             return [
#                 {"type": "Action.Submit", "title": "✅ Yes, Confirm", "data": {"action": "confirm_details"}, "style": "positive"},
#                 {"type": "Action.Submit", "title": "❌ No, Cancel", "data": {"action": "cancel_request"}}
#             ]
#         return [
#             {"type": "Action.Submit", "title": "📝 New Request", "data": {"action": "new_leave_request"}},
#             {"type": "Action.Submit", "title": "📊 Check Balance", "data": {"action": "check_balance"}},
#             {"type": "Action.Submit", "title": "📋 View History", "data": {"action": "view_history"}},
#             {"type": "Action.Submit", "title": "🚪 Logout", "data": {"action": "logout"}, "style": "destructive"}
#         ]

#     @staticmethod
#     def create_login_card() -> Attachment:
#         card_data = {
#             "type": "AdaptiveCard", "version": "1.3",
#             "body": [
#                 {"type": "TextBlock", "text": "🔐 Login Required", "weight": "Bolder", "size": "Large", "color": "Accent"},
#                 {"type": "TextBlock", "text": "Please log in to access the leave management system:", "wrap": True},
#                 {"type": "Input.Text", "id": "employeeId", "label": "Employee ID", "placeholder": "Enter your employee ID"},
#                 {"type": "Input.Text", "id": "password", "label": "Password", "style": "Password", "placeholder": "Enter your password"}
#             ],
#             "actions": [{"type": "Action.Submit", "title": "🚀 Login", "data": {"action": "login"}, "style": "positive"}]
#         }
#         return CardFactory.adaptive_card(card_data)

# class LeaveManagementTeamsBot(ActivityHandler):
#     """Microsoft Teams bot for leave management"""
    
#     def __init__(self, conversation_state: ConversationState, user_state: UserState):
#         self.conversation_state = conversation_state
#         self.user_state = user_state
#         self.active_sessions: Dict[str, SessionData] = {}
    
#     async def on_turn(self, turn_context: TurnContext):
#         await super().on_turn(turn_context)
#         await self.conversation_state.save_changes(turn_context, False)
#         await self.user_state.save_changes(turn_context, False)

#     async def on_message_activity(self, turn_context: TurnContext):
#         try:
#             user_id = turn_context.activity.from_property.id
#             session_data = self.active_sessions.get(user_id)
#             if turn_context.activity.value:
#                 await self._handle_adaptive_card_submit(turn_context, user_id, session_data)
#                 return
#             if not session_data or not session_data.auth_token:
#                 await self._handle_unauthenticated_user(turn_context)
#                 return
#             user_message = turn_context.activity.text.strip()
#             await self._send_typing_indicator(turn_context)
#             result = await self._process_with_agent_graph(user_message, session_data)
#             if result.get("success"):
#                 response_card = AdaptiveCardFactory.create_response_card(result["response"], result.get("conversation_state", {}))
#                 session_data.last_activity = datetime.now()
#                 await turn_context.send_activity(MessageFactory.attachment(response_card))
#             else:
#                 await turn_context.send_activity(MessageFactory.text(f"❌ {result.get('error', 'An error occurred.')}"))
#         except Exception as e:
#             logger.error(f"Error in on_message_activity: {str(e)}", exc_info=True)
#             await turn_context.send_activity(MessageFactory.text("I encountered an error. Please try again or contact support."))
    
#     async def _handle_adaptive_card_submit(self, turn_context: TurnContext, user_id: str, session_data: Optional[SessionData]):
#         card_data = turn_context.activity.value
#         action = card_data.get('action')
#         if action == 'login':
#             await self._handle_login(turn_context, user_id, card_data)
#         elif action == 'logout':
#             await self._handle_logout(turn_context, user_id)
#         elif not session_data or not session_data.auth_token:
#             await self._handle_unauthenticated_user(turn_context)
#         elif action in ['confirm_details', 'cancel_request', 'new_leave_request', 'check_balance', 'view_history']:
#             await self._handle_action_buttons(turn_context, user_id, action, session_data)
    
#     async def _handle_login(self, turn_context: TurnContext, user_id: str, card_data: Dict):
#         employee_id = card_data.get('employeeId', '').strip()
#         password = card_data.get('password', '').strip()
#         if not employee_id or not password:
#             await turn_context.send_activity(MessageFactory.text("❌ Please provide both Employee ID and Password."))
#             return
#         if excel_handler.verify_credentials(employee_id, password):
#             token = create_token(employee_id)
#             self.active_sessions[user_id] = SessionData(employee_id=employee_id, auth_token=token, last_activity=datetime.now())
#             employee_info = excel_handler.get_employee_data(employee_id)
#             employee_name = employee_info.get('name', 'Employee') if employee_info else 'Employee'
#             welcome_message = f"✅ **Welcome, {employee_name}!**\n\nYou're now logged in. How can I help you today?"
#             response_card = AdaptiveCardFactory.create_response_card(welcome_message, {"current_flow": "initial"})
#             await turn_context.send_activity(MessageFactory.attachment(response_card))
#         else:
#             await turn_context.send_activity(MessageFactory.text("❌ Invalid credentials. Please try again."))

#     async def _handle_logout(self, turn_context: TurnContext, user_id: str):
#         if user_id in self.active_sessions:
#             del self.active_sessions[user_id]
#             await turn_context.send_activity(MessageFactory.text("✅ You have been successfully logged out."))
#         await self._handle_unauthenticated_user(turn_context)
    
#     async def _handle_action_buttons(self, turn_context: TurnContext, user_id: str, action: str, session_data: SessionData):
#         action_messages = {
#             'new_leave_request': 'I want to apply for leave',
#             'confirm_details': 'yes',
#             'cancel_request': 'no, cancel',
#             'check_balance': 'What is my current leave balance?',
#             'view_history': 'Show me my leave history'
#         }
#         message = action_messages.get(action)
#         if not message:
#             await turn_context.send_activity(MessageFactory.text(f"Action '{action}' is not recognized."))
#             return
#         await self._send_typing_indicator(turn_context)
#         result = await self._process_with_agent_graph(message, session_data)
#         if result.get("success"):
#             response_card = AdaptiveCardFactory.create_response_card(result["response"], result.get("conversation_state", {}))
#             session_data.last_activity = datetime.now()
#             await turn_context.send_activity(MessageFactory.attachment(response_card))
#         else:
#             await turn_context.send_activity(MessageFactory.text(f"❌ {result.get('error', 'Failed to process your request.')}"))

#     async def _process_with_agent_graph(self, message: str, session_data: SessionData) -> Dict[str, Any]:
#         try:
#             config = {"configurable": {"thread_id": session_data.employee_id}}
#             graph_input = {"messages": [HumanMessage(content=message)]}
#             final_state = None
#             for chunk in graph.stream(graph_input, config, stream_mode="values"):
#                 final_state = chunk
#             if final_state and final_state.get("messages"):
#                 response_content = final_state["messages"][-1].content
#             else:
#                 response_content = "Sorry, I couldn't get a response. Please try again."
#                 final_state = {}
#             gathered_details = {
#                 "Leave Type": final_state.get("leave_type"),
#                 "Start Date": final_state.get("start_date"),
#                 "End Date": final_state.get("end_date"),
#             }
#             conversation_state_details = {
#                 "current_flow": final_state.get("next_node", "END"),
#                 "confirmation_pending": final_state.get("next_node") == "leave_submit",
#                 "gathered_details": {k: v for k, v in gathered_details.items() if v}
#             }
#             return {
#                 "response": response_content,
#                 "conversation_state": conversation_state_details,
#                 "success": True,
#             }
#         except Exception as e:
#             logger.error(f"Error processing with agent graph for user {session_data.employee_id}: {str(e)}", exc_info=True)
#             return {"success": False, "error": "An internal error occurred while processing your request."}
    
#     async def _handle_unauthenticated_user(self, turn_context: TurnContext):
#         login_card = AdaptiveCardFactory.create_login_card()
#         await turn_context.send_activity(MessageFactory.attachment(login_card))
    
#     async def _send_typing_indicator(self, turn_context: TurnContext):
#         await turn_context.send_activity(Activity(type=ActivityTypes.typing))
    
#     async def on_members_added_activity(self, members_added: List[ChannelAccount], turn_context: TurnContext):
#         for member in members_added:
#             if member.id != turn_context.activity.recipient.id:
#                 await turn_context.send_activity(MessageFactory.text("👋 **Welcome to the HR Assistant Bot!**"))
#                 await self._handle_unauthenticated_user(turn_context)

# # --- Application Setup ---
# SETTINGS = BotFrameworkAdapterSettings(
#     app_id=os.getenv("MICROSOFT_APP_ID", ""),
#     app_password=os.getenv("MICROSOFT_APP_PASSWORD", "")
# )
# ADAPTER = BotFrameworkAdapter(SETTINGS)
# BOT = LeaveManagementTeamsBot(ConversationState(MemoryStorage()), UserState(MemoryStorage()))

# # --- Request Handler ---
# async def messages(req: Request) -> Response:
#     if "application/json" not in req.headers.get("Content-Type", ""):
#         return Response(status=415)
#     body = await req.json()
#     activity = Activity().deserialize(body)
#     auth_header = req.headers.get("Authorization", "")
#     try:
#         await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
#         return Response(status=200)
#     except Exception as e:
#         logger.error(f"Error processing message: {str(e)}", exc_info=True)
#         return Response(status=500, text=str(e))

# def create_app():
#     app = web.Application()
#     app.router.add_post("/api/messages", messages)
#     return app

# # --- Main Execution ---
# async def main():
#     app = create_app()
#     runner = web.AppRunner(app)
#     await runner.setup()
#     site = web.TCPSite(runner, 'localhost', Config.BOT_PORT)
#     await site.start()
#     logger.info(f"Teams Bot is listening on http://localhost:{Config.BOT_PORT}/api/messages")
#     while True:
#         await asyncio.sleep(3600)

# if __name__ == "__main__":
#     try:
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         print("Bot stopped manually.")
