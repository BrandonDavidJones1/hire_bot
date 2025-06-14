import discord
import os
import asyncio
import re # For email validation
from dotenv import load_dotenv
import time # For token expiry
import json # For API payloads

# Attempt to import aiohttp, guide user if not found
try:
    import aiohttp
except ImportError:
    print("ERROR: 'aiohttp' library not found. Please install it using: pip install aiohttp")
    print("       This library is required for Adobe Sign API integration.")
    exit()


# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# --- Configuration for Roles and IDs ---
ceo_id_str = os.getenv('CEO_USER_ID')
CEO_USER_ID = int(ceo_id_str) if ceo_id_str and ceo_id_str.strip().isdigit() else None
CEO_CONTACT_DISPLAY_NAME = "Corey LTS (CEO)"

dev_id_str = os.getenv('DEV_USER_ID')
DEV_USER_ID = int(dev_id_str) if dev_id_str and dev_id_str.strip().isdigit() else None
ACTUAL_DEV_CONTACT_NAME = os.getenv('DEV_CONTACT_NAME_ENV', 'the Developer')

TRAINING_MANUAL_URL = os.getenv('TRAINING_MANUAL_URL', 'https://example.com/manual')
TRAINING_VIDEO_URL = os.getenv('TRAINING_VIDEO_URL', 'https://example.com/video')
TRAINING_RECORDINGS_URL = os.getenv('TRAINING_RECORDINGS_URL', 'https://example.com/recordings')
LTS_DISCORD_SERVER_INVITE_URL = os.getenv('LTS_DISCORD_SERVER_INVITE_URL', 'https://discord.gg/defaultinvite')


# --- Adobe Sign Configuration ---
ADOBE_SIGN_CLIENT_ID = os.getenv('ADOBE_SIGN_CLIENT_ID')
ADOBE_SIGN_CLIENT_SECRET = os.getenv('ADOBE_SIGN_CLIENT_SECRET')
ADOBE_SIGN_API_HOST = os.getenv('ADOBE_SIGN_API_HOST') # e.g., 'api.na1.adobesign.com' (without https://)
ADOBE_SIGN_OAUTH_TOKEN_URL = os.getenv('ADOBE_SIGN_OAUTH_TOKEN_URL') # Full URL, e.g., https://secure.na1.adobesign.com/oauth/v2/token
ADOBE_SIGN_API_BASE_PATH = "/api/rest/v6" # Common for v6 API
ICA_TEMPLATE_PATH = os.getenv('ICA_TEMPLATE_PATH', 'IndependentContractorAgreement_Template.pdf') # Path to your PDF template
ICA_TEMPLATE_FILENAME = os.path.basename(ICA_TEMPLATE_PATH) if ICA_TEMPLATE_PATH else "IndependentContractorAgreement_Template.pdf"

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.dm_messages = True
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
user_onboarding_states = {}

# --- Adobe Sign API Global Variables (for simple token management) ---
_ADOBE_ACCESS_TOKEN = None
_ADOBE_TOKEN_EXPIRES_AT = 0

ONBOARDING_STEPS = [
    'start', 'collect_first_name', 'collect_last_name', 'check_computer_response',
    'ask_bilingual', 'check_bilingual_response', 'ask_languages', 'ask_state',
    'ask_email', # Data collection ends, then contract
    'final_instructions_pre_contract',      # Sends DECLARATION
    'awaiting_sign_contract_command',       # Waits for 'sign contract'
    'awaiting_adobe_signature_completion',  # Waits for 'contract signed' after URL is sent
    # Post-contract steps, triggered by 'contract signed' command
    'ask_add_friends',                      # New: Ask to add friends (formerly step 5)
    'check_add_friends_response',           # Bot expects Y/N
    'provide_training_materials',           # New: Provide training (formerly step 6)
    'confirm_training_completion',          # Bot expects 'DONE' (formerly step 7)
    # CEO notification for training completion happens here, then bot proceeds
    'final_welcome_and_discord_link',       # New final step
    'completed'
]

# --- Adobe Sign API Helper Functions (Stubs - Implement with actual API calls) ---

async def get_adobe_access_token():
    """
    Retrieves an Adobe Sign access token using Client Credentials Grant.
    Manages token caching and renewal.
    """
    global _ADOBE_ACCESS_TOKEN, _ADOBE_TOKEN_EXPIRES_AT

    if not all([ADOBE_SIGN_CLIENT_ID, ADOBE_SIGN_CLIENT_SECRET, ADOBE_SIGN_OAUTH_TOKEN_URL]):
        print("ERROR: Adobe Sign Client ID, Client Secret, or OAuth Token URL not configured.")
        raise ValueError("Adobe Sign API credentials not configured.")

    current_time = time.time()
    if _ADOBE_ACCESS_TOKEN and current_time < _ADOBE_TOKEN_EXPIRES_AT:
        print("DEBUG: Using cached Adobe Sign access token.")
        return _ADOBE_ACCESS_TOKEN

    print("DEBUG: Fetching new Adobe Sign access token...")
    payload = {
        'grant_type': 'client_credentials',
        'client_id': ADOBE_SIGN_CLIENT_ID,
        'client_secret': ADOBE_SIGN_CLIENT_SECRET,
        'scope': 'agreement_read agreement_write agreement_send transient_document_write user_read' # Adjust scopes as needed
    }
    # async with aiohttp.ClientSession() as session:
    #     try:
    #         async with session.post(ADOBE_SIGN_OAUTH_TOKEN_URL, data=payload) as resp:
    #             if resp.status == 200:
    #                 token_data = await resp.json()
    #                 _ADOBE_ACCESS_TOKEN = token_data.get('access_token')
    #                 expires_in = token_data.get('expires_in', 3600) # Default to 1 hour
    #                 _ADOBE_TOKEN_EXPIRES_AT = time.time() + expires_in - 60 # Subtract 60s buffer
    #                 print(f"DEBUG: New Adobe Sign access token obtained. Expires in {expires_in}s.")
    #                 return _ADOBE_ACCESS_TOKEN
    #             else:
    #                 error_text = await resp.text()
    #                 print(f"ERROR: Failed to get Adobe Sign access token. Status: {resp.status}, Response: {error_text}")
    #                 raise Exception(f"Adobe Token Error: {resp.status} - {error_text}")
    #     except aiohttp.ClientConnectorError as e:
    #         print(f"ERROR: Adobe Sign token - Connection error: {e}")
    #         raise Exception(f"Adobe Token Connection Error: {e}")

    # --- MOCK IMPLEMENTATION ---
    print("MOCK: Simulating Adobe Access Token retrieval.")
    if ADOBE_SIGN_CLIENT_ID == "test_client_id_fail_token": # For testing failure
        raise Exception("Mock Adobe Token Error: Simulated token failure.")
    _ADOBE_ACCESS_TOKEN = "mock_adobe_access_token_12345"
    _ADOBE_TOKEN_EXPIRES_AT = time.time() + 3600
    return _ADOBE_ACCESS_TOKEN
    # --- END MOCK ---

async def upload_transient_document(access_token, file_path, file_name):
    """
    Uploads a document to Adobe Sign for temporary use in an agreement.
    Returns the transientDocumentId.
    """
    if not os.path.exists(file_path):
        print(f"ERROR: ICA Template PDF not found at path: {file_path}")
        raise FileNotFoundError(f"ICA Template PDF not found: {file_path}")

    upload_url = f"https://{ADOBE_SIGN_API_HOST}{ADOBE_SIGN_API_BASE_PATH}/transientDocuments"
    headers = {'Authorization': f'Bearer {access_token}'}
    
    form_data = aiohttp.FormData()
    form_data.add_field('File',
                        open(file_path, 'rb'),
                        filename=file_name,
                        content_type='application/pdf')

    print(f"DEBUG: Uploading transient document '{file_name}' from '{file_path}' to Adobe Sign.")
    # async with aiohttp.ClientSession() as session:
    #     try:
    #         async with session.post(upload_url, headers=headers, data=form_data) as resp:
    #             if resp.status == 201: # 201 Created
    #                 response_data = await resp.json()
    #                 transient_id = response_data.get('transientDocumentId')
    #                 print(f"DEBUG: Transient document uploaded. ID: {transient_id}")
    #                 return transient_id
    #             else:
    #                 error_text = await resp.text()
    #                 print(f"ERROR: Failed to upload transient document. Status: {resp.status}, Response: {error_text}")
    #                 raise Exception(f"Adobe Upload Error: {resp.status} - {error_text}")
    #     except aiohttp.ClientConnectorError as e:
    #         print(f"ERROR: Adobe Sign upload - Connection error: {e}")
    #         raise Exception(f"Adobe Upload Connection Error: {e}")

    # --- MOCK IMPLEMENTATION ---
    print("MOCK: Simulating Transient Document upload.")
    if file_name == "fail_upload.pdf":
        raise Exception("Mock Adobe Upload Error: Simulated upload failure.")
    return "mock_transient_document_id_67890"
    # --- END MOCK ---

async def create_adobe_agreement(access_token, transient_document_id, agreement_name, signer_email, signer_first_name, signer_last_name):
    """
    Creates an agreement in Adobe Sign using a transient document.
    State is set to "AUTHORING" as per user's example flow.
    Returns the agreementId.
    """
    agreement_url = f"https://{ADOBE_SIGN_API_HOST}{ADOBE_SIGN_API_BASE_PATH}/agreements"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    payload = {
        "fileInfos": [
            {"transientDocumentId": transient_document_id}
        ],
        "name": agreement_name,
        "participantSetsInfo": [
            {
                "memberInfos": [
                    {
                        "email": signer_email,
                        "firstName": signer_first_name, 
                        "lastName": signer_last_name    
                    }
                ],
                "order": 1, 
                "role": "SIGNER"
            }
        ],
        "signatureType": "ESIGN",
        "state": "AUTHORING" 
    }
    print(f"DEBUG: Creating Adobe Sign agreement '{agreement_name}' for {signer_email}.")
    # async with aiohttp.ClientSession() as session:
    #     try:
    #         async with session.post(agreement_url, headers=headers, json=payload) as resp:
    #             if resp.status == 201: # 201 Created
    #                 response_data = await resp.json()
    #                 agreement_id = response_data.get('id')
    #                 print(f"DEBUG: Adobe Sign agreement created. ID: {agreement_id}")
    #                 return agreement_id
    #             else:
    #                 error_text = await resp.text()
    #                 print(f"ERROR: Failed to create Adobe Sign agreement. Status: {resp.status}, Response: {error_text}")
    #                 raise Exception(f"Adobe Agreement Error: {resp.status} - {error_text}")
    #     except aiohttp.ClientConnectorError as e:
    #         print(f"ERROR: Adobe Sign agreement - Connection error: {e}")
    #         raise Exception(f"Adobe Agreement Connection Error: {e}")

    # --- MOCK IMPLEMENTATION ---
    print("MOCK: Simulating Agreement Creation.")
    if agreement_name == "Fail Agreement":
        raise Exception("Mock Adobe Agreement Error: Simulated agreement creation failure.")
    return "mock_agreement_id_abcde"
    # --- END MOCK ---

async def get_adobe_signing_url_for_signer(access_token, agreement_id, expected_signer_email):
    """
    Retrieves the signing URL for a specific signer of an agreement.
    """
    signing_urls_endpoint = f"https://{ADOBE_SIGN_API_HOST}{ADOBE_SIGN_API_BASE_PATH}/agreements/{agreement_id}/signingUrls"
    headers = {'Authorization': f'Bearer {access_token}'}

    print(f"DEBUG: Getting signing URLs for agreement ID {agreement_id}.")
    # async with aiohttp.ClientSession() as session:
    #     try:
    #         async with session.get(signing_urls_endpoint, headers=headers) as resp:
    #             if resp.status == 200:
    #                 response_data = await resp.json()
    #                 for url_set_info in response_data.get("signingUrlSetInfos", []):
    #                     for signing_url_info in url_set_info.get("signingUrls", []):
    #                         if signing_url_info.get("email").lower() == expected_signer_email.lower():
    #                             esign_url = signing_url_info.get("esignUrl")
    #                             print(f"DEBUG: Found signing URL for {expected_signer_email}: {esign_url}")
    #                             return esign_url
    #                 print(f"ERROR: Signing URL not found for {expected_signer_email} in agreement {agreement_id}.")
    #                 raise Exception(f"Adobe Signing URL not found for signer.")
    #             else:
    #                 error_text = await resp.text()
    #                 print(f"ERROR: Failed to get signing URLs. Status: {resp.status}, Response: {error_text}")
    #                 raise Exception(f"Adobe Signing URL Error: {resp.status} - {error_text}")
    #     except aiohttp.ClientConnectorError as e:
    #         print(f"ERROR: Adobe Sign signing URL - Connection error: {e}")
    #         raise Exception(f"Adobe Signing URL Connection Error: {e}")

    # --- MOCK IMPLEMENTATION ---
    print("MOCK: Simulating Signing URL retrieval.")
    if agreement_id == "fail_signing_url_retrieval":
        raise Exception("Mock Adobe Signing URL Error: Simulated URL retrieval failure.")
    return f"https://mock.adobesign.com/public/apiesign?pid=mock_pid_for_{expected_signer_email.replace('@','_at_')}"
    # --- END MOCK ---

# --- Onboarding Logic ---
async def send_onboarding_message(user_id, step_name_override=None):
    if user_id not in user_onboarding_states:
        print(f"User {user_id} not in onboarding states. Cannot send message.")
        return

    state = user_onboarding_states[user_id]
    current_step_name = step_name_override if step_name_override else state['step']
    
    user = None
    try:
        user = await client.fetch_user(user_id)
    except discord.NotFound:
        print(f"Error: Could not fetch user {user_id} (User not found). Removing from onboarding.")
        if user_id in user_onboarding_states: del user_onboarding_states[user_id]
        return
    except Exception as e:
        print(f"Error: Could not fetch user {user_id} due to an unexpected error: {e}. Removing from onboarding.")
        if user_id in user_onboarding_states: del user_onboarding_states[user_id]
        return

    message_content = ""
    next_step_in_flow = "" # This will be set by the specific block that intends to send a message and advance state

    print(f"Processing step '{current_step_name}' for user {user.name} ({user_id})")

    if current_step_name == 'start':
        message_content = (
            "Welcome to the New Hire Onboarding Process!\n"
            "I'm your friendly training bot. I'll guide you through the initial steps.\n\n"
            "Please reply directly to my messages here in our DM.\n\n"
            "Let's start with your name. What is your legal first name?"
        )
        next_step_in_flow = 'collect_first_name'
    
    elif current_step_name == 'collect_first_name':
        message_content = "Thank you. And what is your legal last name?"
        next_step_in_flow = 'collect_last_name'

    elif current_step_name == 'collect_last_name':
        message_content = "1. Do you have a computer or laptop (not an iPad or tablet) and headset that you will be using for work? (Y/N)"
        next_step_in_flow = 'check_computer_response'

    elif current_step_name == 'ask_bilingual':
        message_content = "2. Are you bilingual? (Y/N)"
        next_step_in_flow = 'check_bilingual_response'

    elif current_step_name == 'check_bilingual_response':
        is_bilingual = state['data'].get('bilingual', False)
        if is_bilingual:
            message_content = "Great! What languages do you speak fluently (besides English, if applicable)?"
            next_step_in_flow = 'ask_languages'
        else:
            message_content = "3. In which state are you located?"
            next_step_in_flow = 'ask_state'

    elif current_step_name == 'ask_languages':
        message_content = "3. In which state are you located?"
        next_step_in_flow = 'ask_state'

    elif current_step_name == 'ask_state':
        message_content = "4. What is your primary email address?"
        next_step_in_flow = 'ask_email'

    elif current_step_name == 'ask_email':
        message_content = "4. What is your primary email address? (This is where your contract will be sent)"
        next_step_in_flow = 'ask_email' # Stay in this state, on_message will collect & advance
    
    elif current_step_name == 'final_instructions_pre_contract':
        message_content = (
            "DECLARATION. I hereby declare that the information I am providing in the Adobe eSign documents is true to the best of my knowledge and belief and nothing has been concealed therein. I understand that if the information provided by me is proved false/not true, I will have to face the punishment as per the law.\n\n"
            "To proceed with your Independent Contractor Agreement using Adobe Sign, please type `sign contract` back to me."
        )
        next_step_in_flow = 'awaiting_sign_contract_command'

    # --- POST-CONTRACT STEPS ---
    elif current_step_name == 'ask_add_friends': # This is after 'contract signed'
        friends_to_add_list = ["- Adam Black (Support)"]
        if CEO_USER_ID:
            friends_to_add_list.append(f"- {CEO_CONTACT_DISPLAY_NAME}")
        
        friends_to_add_str = "\n".join(friends_to_add_list)

        message_content = (
            "Great! Your contract process has been initiated.\n\n"
            "Now, for the next steps:\n"
            "1. Please add the following users as friends:\n"
            f"{friends_to_add_str}\n\n"
            "Have you done this? (Y/N)"
        )
        next_step_in_flow = 'check_add_friends_response'
    
    elif current_step_name == 'check_add_friends_response': 
        # This state is an intermediate; on_message handles the Y/N and calls provide_training_materials.
        # So no message_content is sent directly from here by send_onboarding_message.
        pass 

    elif current_step_name == 'provide_training_materials':
        message_content = (
            "2. Next, please complete the following training materials:\n"
            f"   - Read the Training Manual: {TRAINING_MANUAL_URL}\n"
            f"   - Watch the Training Video: {TRAINING_VIDEO_URL}\n"
            f"   - Listen to Training Recordings: {TRAINING_RECORDINGS_URL}\n\n"
            "Once you have completed ALL of these, please reply with 'DONE'."
        )
        next_step_in_flow = 'confirm_training_completion'

    elif current_step_name == 'confirm_training_completion':
        # This block is executed when on_message gets 'DONE'.
        # It sends notifications to staff and then immediately transitions to the final welcome message for the user.
        summary = (
            f"New Hire Onboarding Information for: {state['data'].get('first_name', 'N/A')} {state['data'].get('last_name', 'N/A')} ({user.name}, ID: {user.id})\n"
            f"--------------------------------------------------\n"
            f"Has Computer/Laptop: {'Yes' if state['data'].get('has_computer') else 'No'}\n"
            f"Bilingual: {'Yes' if state['data'].get('bilingual') else 'No'}\n"
        )
        if state['data'].get('languages'):
            summary += f"Languages: {state['data']['languages']}\n"
        summary += (
            f"State: {state['data'].get('state', 'N/A')}\n"
            f"Email: {state['data'].get('email', 'N/A')}\n"
            f"Contract Process Initiated: Yes (Adobe Agreement ID: {state['data'].get('adobe_agreement_id', 'N/A')})\n"
            f"Added Friends: {'Yes' if state['data'].get('added_friends') else 'No, or not confirmed'}\n"
            f"Training Completed: Yes\n"
            f"--------------------------------------------------\n"
            f"This user has completed the training materials after contract initiation. "
            f"The bot will now provide them with final instructions and the server link."
        )

        # --- Staff Notification Logic ---
        failed_to_notify_descriptors = [] 
        state['data']['_notification_attempted_ceo_training'] = False
        state['data']['_successfully_notified_ceo_training'] = False
        state['data']['_notification_attempted_dev_training'] = False
        state['data']['_successfully_notified_dev_training'] = False

        if CEO_USER_ID:
            state['data']['_notification_attempted_ceo_training'] = True
            ceo_user_to_notify = None
            try:
                ceo_user_to_notify = await client.fetch_user(CEO_USER_ID)
                if ceo_user_to_notify:
                    await ceo_user_to_notify.send(summary)
                    state['data']['_successfully_notified_ceo_training'] = True
                    print(f"Successfully sent training completion summary to {CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID}) for user {user.name}.")
                else: 
                    failed_to_notify_descriptors.append(f"{CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID} - User object not obtained)")
            except discord.NotFound:
                failed_to_notify_descriptors.append(f"{CEO_CONTACT_DISPLAY_NAME} (User ID {CEO_USER_ID} not found)")
            except discord.Forbidden:
                failed_to_notify_descriptors.append(f"{CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID} - DMs disabled)")
            except Exception as e:
                failed_to_notify_descriptors.append(f"{CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID} - Error: {e})")
        
        if DEV_USER_ID:
            state['data']['_notification_attempted_dev_training'] = True
            dev_user_to_notify = None
            try:
                dev_user_to_notify = await client.fetch_user(DEV_USER_ID)
                if dev_user_to_notify:
                    await dev_user_to_notify.send(summary)
                    state['data']['_successfully_notified_dev_training'] = True
                    print(f"Successfully sent training completion summary to Developer (ID: {DEV_USER_ID}) for user {user.name}.")
                else:
                     failed_to_notify_descriptors.append(f"{ACTUAL_DEV_CONTACT_NAME} (ID: {DEV_USER_ID} - User object not obtained)")
            except discord.NotFound:
                print(f"Failed to find Developer (ID: {DEV_USER_ID}) to send training summary for {user.name}.")
                failed_to_notify_descriptors.append(f"{ACTUAL_DEV_CONTACT_NAME} (ID: {DEV_USER_ID} - User not found)")
            except discord.Forbidden:
                print(f"Failed to send training summary to Developer (ID: {DEV_USER_ID}) for {user.name} - DMs disabled.")
                failed_to_notify_descriptors.append(f"{ACTUAL_DEV_CONTACT_NAME} (ID: {DEV_USER_ID} - DMs disabled)")
            except Exception as e:
                print(f"Error sending training summary to Developer (ID: {DEV_USER_ID}) for {user.name}: {e}")
                failed_to_notify_descriptors.append(f"{ACTUAL_DEV_CONTACT_NAME} (ID: {DEV_USER_ID} - Error: {e})")
        
        print(f"User {user.name} ({user_id}) completed training. Staff notification process complete. Proceeding to final welcome message.")
        if failed_to_notify_descriptors:
            print(f"Note: Issues notifying staff for user {user.name}: {', '.join(failed_to_notify_descriptors)}")

        # Update state and trigger the next message sending (final welcome)
        user_onboarding_states[user_id]['step'] = 'final_welcome_and_discord_link'
        await send_onboarding_message(user_id, step_name_override='final_welcome_and_discord_link')
        return # Crucial: prevent this block from trying to send its own message_content as it's handled by recursive call
    
    elif current_step_name == 'final_welcome_and_discord_link':
        message_content = (
            "Welcome aboard officially!\n\n"
            "Your final steps are:\n"
            f"- Please contact {CEO_CONTACT_DISPLAY_NAME} for your next assignments and to get fully integrated.\n"
            "- Adam Black is your human contact for project specific questions and quality control.\n"
            "- Samantha is your Discord training and agent support bot on the main server. You can start by telling Samantha that you've finished your onboarding training.\n"
            f"- Here is the link to the LTS Discord Server: {LTS_DISCORD_SERVER_INVITE_URL}\n\n"
            "This fully concludes your automated onboarding with me. Welcome officially to the team! "
        )
        next_step_in_flow = 'completed'

    if message_content: 
        try:
            await user.send(message_content)
            if next_step_in_flow:
                 user_onboarding_states[user_id]['step'] = next_step_in_flow
                 print(f"User {user.name} advanced to step: {next_step_in_flow}")
            
            # Check if new state is 'completed' and clean up
            # Need to check if user_id still exists in states, as a recursive call might have already deleted it
            if user_id in user_onboarding_states and user_onboarding_states[user_id]['step'] == 'completed':
                print(f"Onboarding fully completed for user {user.name}. Removing from active states.")
                del user_onboarding_states[user_id]
        except discord.Forbidden:
            print(f"Could not send DM to {user.name} ({user_id}). DMs disabled or bot blocked.")
        except Exception as e:
            print(f"Error sending DM to {user.name}: {e}")

@client.event
async def on_ready():
    print(f'Logged in as {client.user.name} ({client.user.id})')
    print('------')
    
    if CEO_USER_ID: print(f"INFO: CEO notifications will be sent to: {CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID}).")
    else: print("WARNING: CEO_USER_ID is not set. CEO notifications will not be sent.")
    if DEV_USER_ID: print(f"INFO: Developer notifications will be sent to: {ACTUAL_DEV_CONTACT_NAME} (ID: {DEV_USER_ID}).")
    else: print("INFO: DEV_USER_ID is not set. Developer notifications will not be sent.")
    if LTS_DISCORD_SERVER_INVITE_URL == 'https://discord.gg/defaultinvite' or not LTS_DISCORD_SERVER_INVITE_URL:
        print(f"WARNING: LTS_DISCORD_SERVER_INVITE_URL is set to default or empty. Please update in .env file.")
    else:
        print(f"INFO: LTS Discord Server Invite URL: {LTS_DISCORD_SERVER_INVITE_URL}")


    print("--- Adobe Sign Configuration ---")
    adobe_config_ok = True
    if not ADOBE_SIGN_CLIENT_ID: print("WARNING: ADOBE_SIGN_CLIENT_ID not set."); adobe_config_ok = False
    if not ADOBE_SIGN_CLIENT_SECRET: print("WARNING: ADOBE_SIGN_CLIENT_SECRET not set."); adobe_config_ok = False
    if not ADOBE_SIGN_API_HOST: print("WARNING: ADOBE_SIGN_API_HOST not set."); adobe_config_ok = False
    if not ADOBE_SIGN_OAUTH_TOKEN_URL: print("WARNING: ADOBE_SIGN_OAUTH_TOKEN_URL not set."); adobe_config_ok = False
    if not ICA_TEMPLATE_PATH or not os.path.exists(ICA_TEMPLATE_PATH):
        print(f"WARNING: ICA_TEMPLATE_PATH ('{ICA_TEMPLATE_PATH}') not set or file does not exist."); adobe_config_ok = False
    
    if adobe_config_ok:
        print("INFO: Adobe Sign basic configuration appears present.")
        print(f"INFO: Using ICA Template: {ICA_TEMPLATE_PATH}")
    else:
        print("ERROR: Adobe Sign is not fully configured. Contract signing via Adobe Sign will likely fail.")
    print('------')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if isinstance(message.channel, discord.DMChannel):
        user_id = message.author.id
        processed_message_content = message.content.lower().strip()

        if processed_message_content == 'start':
            if user_id in user_onboarding_states and user_onboarding_states[user_id].get('step') == 'completed':
                del user_onboarding_states[user_id] 

            if user_id not in user_onboarding_states:
                print(f"Starting onboarding for user {message.author.name} ({user_id}) via 'start' command")
                user_onboarding_states[user_id] = {
                    'step': 'start', 'data': {}, 'dm_channel_id': message.channel.id
                }
                await send_onboarding_message(user_id)
            else:
                await message.channel.send("You are already in the onboarding process. Reply to my last question or type `reset` to start over.")
            return

        if processed_message_content == 'reset':
            if user_id in user_onboarding_states:
                del user_onboarding_states[user_id]
                await message.channel.send("Your onboarding state has been reset. Type `start` to begin again.")
            else:
                await message.channel.send("You are not currently in an onboarding process to reset.")
            return

        if processed_message_content == 'complete': # Largely deprecated command
            if user_id in user_onboarding_states:
                current_user_step = user_onboarding_states[user_id]['step']
                await message.channel.send(f"The `complete` command is not needed at this stage ('{current_user_step}'). Please follow the current instructions or reply to my last question.")
            else:
                await message.channel.send("You are not currently in an onboarding stage where the `complete` command is applicable.")
            return

        if processed_message_content == 'sign contract':
            if user_id in user_onboarding_states and user_onboarding_states[user_id]['step'] == 'awaiting_sign_contract_command':

                await message.channel.send("Thank you. I will now prepare your Independent Contractor Agreement using Adobe Sign. This may take a moment...")
                
                user_data = user_onboarding_states[user_id]['data']
                user_email = user_data.get('email', 'not_provided@example.com')
                user_first_name = user_data.get('first_name', 'Valued')
                user_last_name = user_data.get('last_name', 'Contractor')
                agreement_name = f"Independent Contractor Agreement - {user_first_name} {user_last_name} - {time.strftime('%Y-%m-%d')}"

                try:
                    token = await get_adobe_access_token()
                    transient_id = await upload_transient_document(token, ICA_TEMPLATE_PATH, ICA_TEMPLATE_FILENAME)
                    agreement_id = await create_adobe_agreement(token, transient_id, agreement_name, user_email, user_first_name, user_last_name)
                    signing_url = await get_adobe_signing_url_for_signer(token, agreement_id, user_email)

                    user_onboarding_states[user_id]['data']['adobe_agreement_id'] = agreement_id

                    await message.channel.send(
                        "Your Independent Contractor Agreement is ready to be signed.\n\n"
                        "Please click the link below to review and sign the document through Adobe Sign:\n"
                        f"{signing_url}\n\n"
                        "Once you have completed the signing process, please return here and type `contract signed`."
                    )
                    user_onboarding_states[user_id]['step'] = 'awaiting_adobe_signature_completion'
                    print(f"Successfully initiated Adobe Sign agreement {agreement_id} for {user_email}. Signing URL sent.")

                except FileNotFoundError as e:
                    await message.channel.send("I'm sorry, I couldn't find the contract template file. Please notify an administrator.")
                    print(f"ERROR: Adobe Sign ICA template file error: {e}")
                except Exception as e:
                    await message.channel.send(f"I encountered an error while trying to prepare your contract with Adobe Sign: {e}. Please try again later or contact an administrator.")
                    print(f"ERROR: Adobe Sign API process failed for user {message.author.name}: {e}")

            elif user_id in user_onboarding_states and user_onboarding_states[user_id]['step'] == 'awaiting_adobe_signature_completion':
                await message.channel.send("I've already sent you the link to sign the contract. Please use that link and then type `contract signed` once you're done.")
            else:
                await message.channel.send("You can use `sign contract` after you've acknowledged the declaration message.")
            return

        if processed_message_content == 'contract signed':
            if user_id in user_onboarding_states and user_onboarding_states[user_id]['step'] == 'awaiting_adobe_signature_completion':
                user_onboarding_states[user_id]['data']['contract_process_completed_by_user'] = True
                user_data = user_onboarding_states[user_id]['data']
                user_email = user_data.get('email', 'N/A')
                first_name = user_data.get('first_name', 'N/A')
                last_name = user_data.get('last_name', 'N/A')
                agreement_id = user_data.get('adobe_agreement_id', 'N/A')

                await message.channel.send(
                    "Thank you for confirming! Your Independent Contractor Agreement is now marked as signed on your end."
                )
                print(f"User {message.author.name} confirmed 'contract signed' for Adobe agreement ID: {agreement_id}.")

                notification_message_for_staff = (
                    f"ALERT: User {first_name} {last_name} (Discord: {message.author.name}, ID: {user_id}, Email: {user_email}) "
                    f"has indicated they have SIGNED the Independent Contractor Agreement (Adobe Agreement ID: {agreement_id}) via Adobe Sign. "
                    f"Please verify the document status in Adobe Sign."
                )
                if CEO_USER_ID:
                    try:
                        ceo_user = await client.fetch_user(CEO_USER_ID)
                        if ceo_user: await ceo_user.send(notification_message_for_staff)
                        print(f"Notified CEO about user confirmation for Adobe Sign agreement {agreement_id}.")
                    except Exception as e: print(f"Failed to notify CEO (Adobe Sign confirm): {e}")
                if DEV_USER_ID:
                    try:
                        dev_user = await client.fetch_user(DEV_USER_ID)
                        if dev_user: await dev_user.send(notification_message_for_staff)
                        print(f"Notified Dev about user confirmation for Adobe Sign agreement {agreement_id}.")
                    except Exception as e: print(f"Failed to notify Dev (Adobe Sign confirm): {e}")
                
                await send_onboarding_message(user_id, step_name_override='ask_add_friends') # Start post-contract steps
            else:
                await message.channel.send("You can use `contract signed` after I've sent you a link to sign the document and you've completed it.")
            return

        if user_id not in user_onboarding_states:
            await message.channel.send("Hello! To begin the onboarding process, please type `start`.")
            return

        state = user_onboarding_states[user_id]
        current_step = state['step']
        response = message.content.strip()

        if current_step == 'collect_first_name':
            if response: 
                state['data']['first_name'] = response
                await send_onboarding_message(user_id, step_name_override='collect_first_name')
            else:
                await message.channel.send("Please provide your legal first name.")
            return
        
        elif current_step == 'collect_last_name':
            if response: 
                state['data']['last_name'] = response
                await send_onboarding_message(user_id, step_name_override='collect_last_name')
            else:
                await message.channel.send("Please provide your legal last name.")
            return

        elif current_step == 'check_computer_response':
            if processed_message_content.upper() == 'Y':
                state['data']['has_computer'] = True
            elif processed_message_content.upper() == 'N':
                state['data']['has_computer'] = False
                await message.channel.send(
                    "A computer or laptop (not an iPad or tablet) is required for this role. "
                    "Unfortunately, we cannot proceed with your onboarding at this time. "
                    "Please contact your hiring manager."
                )
                if user_id in user_onboarding_states: del user_onboarding_states[user_id]
                print(f"Onboarding terminated for {message.author.name} (no computer).")
                return 
            else:
                await message.channel.send("Invalid input. Please answer Y or N.")
                return
            await send_onboarding_message(user_id, step_name_override='ask_bilingual')

        elif current_step == 'check_bilingual_response':
            if processed_message_content.upper() == 'Y':
                state['data']['bilingual'] = True
            elif processed_message_content.upper() == 'N':
                state['data']['bilingual'] = False
            else:
                await message.channel.send("Invalid input. Please answer Y or N.")
                return
            await send_onboarding_message(user_id, step_name_override='check_bilingual_response') 

        elif current_step == 'ask_languages': 
            state['data']['languages'] = response
            await send_onboarding_message(user_id, step_name_override='ask_languages')
            return

        elif current_step == 'ask_state': 
            state['data']['state'] = response 
            normalized_state_input = response.strip().lower()
            restricted_states_map = {
                'oregon': 'OR', 'or': 'OR',
                'washington': 'WA', 'wa': 'WA',
                'california': 'CA', 'ca': 'CA'
            }
            if normalized_state_input in restricted_states_map:
                await message.channel.send(
                    "Thank you for your interest. Unfortunately, we are unable to proceed with your application "
                    "in Oregon, Washington, or California at this time."
                )
                if user_id in user_onboarding_states: del user_onboarding_states[user_id]
                print(f"Onboarding terminated for {message.author.name} (restricted state).")
                return
            else:
                await send_onboarding_message(user_id, step_name_override='ask_state') 
            return

        elif current_step == 'ask_email':
            if re.match(r"[^@]+@[^@]+\.[^@]+", response):
                state['data']['email'] = response
                await send_onboarding_message(user_id, step_name_override='final_instructions_pre_contract') 
            else:
                await message.channel.send("That doesn't look like a valid email address. Please try again.")
            return
        
        elif current_step == 'check_add_friends_response':
            if processed_message_content.upper() == 'Y':
                state['data']['added_friends'] = True
            elif processed_message_content.upper() == 'N':
                state['data']['added_friends'] = False
                await message.channel.send(f"Please ensure you add the required contacts. This is important for team communication.")
            else:
                await message.channel.send("Invalid input. Please answer Y or N.")
                return 
            await send_onboarding_message(user_id, step_name_override='provide_training_materials')
            return

        elif current_step == 'confirm_training_completion':
            if processed_message_content.upper() == 'DONE':
                state['data']['training_completed'] = True
                # This will trigger notifications and then the final welcome message sequence in send_onboarding_message
                await send_onboarding_message(user_id, step_name_override='confirm_training_completion') 
            else:
                await message.channel.send("Please type 'DONE' once you have completed all training materials.")
            return
        
        elif current_step == 'awaiting_sign_contract_command':
            await message.channel.send("Please type `sign contract` to proceed with the agreement, or `reset`.")
            return
        elif current_step == 'awaiting_adobe_signature_completion':
            await message.channel.send("Please use the Adobe Sign link I provided. Once signed, type `contract signed` back here.")
            return
        elif current_step == 'completed':
             await message.channel.send("Your onboarding is complete! Type `reset` then `start` to restart.")
             return


# --- Main Execution ---
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN environment variable not found.")
    else:
        print("Attempting to connect to Discord...")
        if 'aiohttp' not in globals():
             print("FATAL: aiohttp is required but not loaded. Bot cannot start.")
        else:
            try:
                client.run(BOT_TOKEN)
            except discord.LoginFailure:
                print("ERROR: Failed to log in. Check your BOT_TOKEN.")
            except discord.PrivilegedIntentsRequired:
                print("ERROR: Privileged Intents Required. Enable 'SERVER MEMBERS INTENT' and 'MESSAGE CONTENT INTENT' in Discord Developer Portal.")
            except Exception as e:
                print(f"An unexpected error occurred while trying to run the bot: {e}")
