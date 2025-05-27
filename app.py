import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

app = Flask(__name__)

# Initialize Twilio Client
account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
twilio_phone_number = os.environ.get('TWILIO_PHONE_NUMBER')

# Ensure Twilio client is initialized only if credentials are valid
if account_sid and auth_token:
    client = Client(account_sid, auth_token)
else:
    print("ERROR: Twilio credentials not found or incomplete in .env file.")
    client = None # Explicitly set to None if not configured

# In-memory store for user sessions (for simplicity)
user_sessions = {}

# --- LET'S TAKE SURVEYS (LTS) HIRE STEPS ---
hire_steps = [
    {
        "id": "welcome_intro",
        "message": "Welcome to Let's Take Surveys (LTS) a public opinion polling company specializing in conducting political surveys, patches and voter ID campaigns.\n\n**************************\n\nJust a few questions before starting...\n\n(Reply 'OK' or 'Next' to continue)",
        "next_step": "confirm_computer"
    },
    {
        "id": "confirm_computer",
        "question": "Confirming you have a computer/laptop, NOT an iPad or tablet? (Yes/No)",
        "data_key": "has_computer", # We'll store their answer
        "next_step": "bilingual_query"
    },
    {
        "id": "bilingual_query",
        "question": "Bilingual? If so, what languages? (e.g., 'No', or 'Yes, Spanish and French')",
        "data_key": "languages", # We'll store their answer
        "next_step": "confirm_state"
    },
    {
        "id": "confirm_state",
        "question": "Please CONFIRM the state you're located in (e.g., California, New York).",
        "data_key": "user_state", # We'll store their answer
        "next_step": "confirm_email"
    },
    {
        "id": "confirm_email",
        "question": "Be sure to CONFIRM your email address for the next step...",
        "data_key": "user_email", # We'll store their answer
        "next_step": "discord_intro"
    },
    {
        "id": "discord_intro",
        "message": "NEXT STEP\n\nDISCORD is the app we use to communicate at LTS.\n\nCreate an account and set your Display NAME as Az + First & Last name (e.g. AzJohnSmith)\n\nClick the link below to register a discord account:\nhttps://discord.gg/qvvrcSGFZe\n\n(Reply 'DONE' when you've set up Discord)",
        "next_step": "discord_tasks"
    },
    {
        "id": "discord_tasks",
        "message": "Great! Now in Discord:\n\nGo into the Main-Chat & Add \"Adam Black\" and \"Corey LTS\" as friends.\n\nLocate the \"main-chat\" tab. Under it are the following...\n# 1-training-manual (read)\n# 2-training-video (watch)\n# 3-recordings (listen)\n\n(Reply 'TRAINING COMPLETE' once you've finished these tasks)",
        "next_step": "final_step_discord_dm"
    },
    {
        "id": "final_step_discord_dm",
        "message": "Excellent! Once training is completed, DM \"Corey LTS\" on discord and he'll provide the final step! Your initial SMS onboarding is now complete. We have your details:\nComputer: {has_computer}\nLanguages: {languages}\nState: {user_state}\nEmail: {user_email}\n\nWelcome to LTS!",
        # This is a final message. No 'next_step' needed.
        # Placeholders here WILL use session["data"]
    }
]

def get_step_details(step_id):
    for step in hire_steps:
        if step["id"] == step_id:
            return step
    return None

def format_message(message_template, data_dict):
    """Safely formats a message, replacing known placeholders or leaving them if data is missing."""
    # A more robust way could be to use data_dict.get('key', '[undefined]') for each known key
    # For simplicity, we'll try to format and catch KeyErrors for this version,
    # but ideally, ensure data is present or handle missing keys gracefully.
    try:
        return message_template.format(**data_dict)
    except KeyError as e:
        print(f"Warning: KeyError during message formatting: {e}. Placeholder missing in data_dict.")
        # Fallback: return message with unresolved placeholders if critical data is missing
        # Or, you could return a generic error message
        return message_template # Or a more user-friendly error message

@app.route("/sms", methods=['POST'])
def sms_reply():
    incoming_msg_original = request.values.get('Body', '').strip()
    incoming_msg_lower = incoming_msg_original.lower()
    from_number = request.values.get('From', '')

    resp = MessagingResponse()
    reply_text = ""

    if not from_number:
        resp.message("Could not identify sender.")
        return str(resp)

    # Get or initialize user session
    if from_number not in user_sessions:
        first_step_details = hire_steps[0]
        user_sessions[from_number] = {
            "current_step_id": first_step_details["id"],
            "data": {} # IMPORTANT: data starts empty
        }
        session = user_sessions[from_number]
        
        # Send the first message (no data to format in it yet)
        if "message" in first_step_details:
            reply_text = first_step_details["message"]
        elif "question" in first_step_details:
            reply_text = first_step_details["question"]
        else:
            reply_text = "Welcome! System is initializing." # Fallback

        resp.message(reply_text)
        return str(resp)

    # Existing session
    session = user_sessions[from_number]
    current_step_id = session["current_step_id"]
    current_step_details = get_step_details(current_step_id)

    if not current_step_details:
        reply_text = "Sorry, I'm having trouble with our process. Please contact LTS support."
        # Optionally reset session
        # user_sessions[from_number] = {"current_step_id": hire_steps[0]["id"], "data": {}}
        resp.message(reply_text)
        return str(resp)

    # --- Data Collection Logic ---
    # If the current step was a question, the incoming message is the answer to it.
    if "question" in current_step_details and "data_key" in current_step_details:
        session["data"][current_step_details["data_key"]] = incoming_msg_original # Store with original casing

    # --- Advancement Logic ---
    can_proceed = False
    user_input_for_progression = "" # What the user said to make us proceed

    if "question" in current_step_details: # Any reply to a question is an answer, so we proceed
        can_proceed = True
        user_input_for_progression = incoming_msg_lower
    elif "message" in current_step_details: # For message steps, check keywords
        if current_step_id == "welcome_intro" and incoming_msg_lower in ["ok", "next"]:
            can_proceed = True
            user_input_for_progression = incoming_msg_lower
        elif current_step_id == "discord_intro" and incoming_msg_lower == "done":
            can_proceed = True
            user_input_for_progression = incoming_msg_lower
        elif current_step_id == "discord_tasks" and incoming_msg_lower == "training complete":
            can_proceed = True
            user_input_for_progression = incoming_msg_lower
        elif "next_step" not in current_step_details: # It's a final message, no progression needed
            can_proceed = False


    next_step_id_from_current = current_step_details.get("next_step")

    if can_proceed and next_step_id_from_current:
        next_step_details = get_step_details(next_step_id_from_current)
        if next_step_details:
            session["current_step_id"] = next_step_details["id"] # Update session to new step
            if "message" in next_step_details:
                # Pass session["data"] for formatting, relevant for the final message
                reply_text = format_message(next_step_details["message"], session["data"])
            elif "question" in next_step_details:
                # Questions in LTS script do not use placeholders from session["data"]
                reply_text = next_step_details["question"]
            
            # If this new step is the absolute final message (no further next_step)
            if not next_step_details.get("next_step"):
                # Optionally clear session for completed users after some time or condition
                # For now, we keep it to allow them to see the final message again if they text.
                pass
        else: # Should not happen if hire_steps is well-defined
            reply_text = "Process ended unexpectedly (next step not found). Please contact LTS support."
            # user_sessions[from_number] = {"current_step_id": hire_steps[0]["id"], "data": {}} # Reset
    elif "message" in current_step_details and not next_step_id_from_current: # It's a final message step and we're already on it
        reply_text = format_message(current_step_details["message"], session["data"])
    elif not can_proceed and ("message" in current_step_details or "question" in current_step_details):
        # User replied something unexpected or didn't use the proceed keyword for a message step.
        # Re-send the current step's message/question.
        original_prompt = ""
        if "message" in current_step_details:
            original_prompt = format_message(current_step_details["message"], session["data"]) # Final message might have placeholders
        elif "question" in current_step_details:
            original_prompt = current_step_details["question"] # Questions don't have placeholders

        # Add a specific reminder if applicable
        reminder = ""
        if current_step_id == "welcome_intro" and incoming_msg_lower not in ["ok", "next"]:
            reminder = "\n\n(Please reply 'OK' or 'Next' to continue)"
        elif current_step_id == "discord_intro" and incoming_msg_lower != "done":
            reminder = "\n\n(Please reply 'DONE' once you've set up Discord)"
        elif current_step_id == "discord_tasks" and incoming_msg_lower != "training complete":
            reminder = "\n\n(Please reply 'TRAINING COMPLETE' once finished)"
        
        reply_text = original_prompt + reminder
    else:
        # Fallback / Should ideally not be reached if logic covers all cases
        reply_text = "I'm a bit confused by your previous response. Let's try the last step again.\n"
        if "message" in current_step_details:
             reply_text += format_message(current_step_details["message"], session["data"])
        elif "question" in current_step_details:
             reply_text += current_step_details["question"]


    resp.message(reply_text)
    return str(resp)

if __name__ == "__main__":
    if not client: # Check if Twilio client failed to initialize
        print("CRITICAL: Twilio client not initialized. Check .env and credentials. Exiting.")
    else:
        print("Starting Flask server for LTS Hire Bot...")
        # Make sure to use port 5000 if that's what ngrok is forwarding
        app.run(debug=True, port=5000)