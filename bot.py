# --- START OF FILE bot.py ---

import discord
import os
import asyncio
import re # For email validation
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# --- Configuration for Roles and IDs ---
# CEO (Corey LTS)
ceo_id_str = os.getenv('CEO_USER_ID')
CEO_USER_ID = int(ceo_id_str) if ceo_id_str and ceo_id_str.strip().isdigit() else None
CEO_CONTACT_DISPLAY_NAME = "Corey LTS (CEO)"

# Developer (You) - Loaded but not used in user-facing onboarding flow anymore
dev_id_str = os.getenv('DEV_USER_ID')
DEV_USER_ID = int(dev_id_str) if dev_id_str and dev_id_str.strip().isdigit() else None
ACTUAL_DEV_CONTACT_NAME = os.getenv('DEV_CONTACT_NAME_ENV', 'the Developer')

# Adam Black is referred to by name directly in messages.

TRAINING_MANUAL_URL = os.getenv('TRAINING_MANUAL_URL', 'https://example.com/manual')
TRAINING_VIDEO_URL = os.getenv('TRAINING_VIDEO_URL', 'https://example.com/video')
TRAINING_RECORDINGS_URL = os.getenv('TRAINING_RECORDINGS_URL', 'https://example.com/recordings')

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.dm_messages = True
intents.message_content = True
intents.members = True # Needed to fetch user objects reliably

client = discord.Client(intents=intents)

# In-memory storage for user onboarding states
user_onboarding_states = {}

# Conceptual list of steps (actual flow managed by logic)
ONBOARDING_STEPS = [
    'start', 'check_computer_response', 'ask_bilingual', 'check_bilingual_response',
    'ask_languages', 'ask_state', 'ask_email', 'instruct_add_friends',
    'check_add_friends_response', 'provide_training_materials',
    'confirm_training_completion', 'notify_ceo_and_wait', 'final_instructions'
]

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
    next_step_in_flow = ""

    print(f"Processing step '{current_step_name}' for user {user.name} ({user_id})")

    if current_step_name == 'start':
        message_content = (
            "Welcome to the New Hire Onboarding Process!\n"
            "I'm your friendly training bot. I'll guide you through the initial steps.\n\n"
            "Please reply directly to my messages here in our DM.\n\n"
            "1. Do you have a computer or laptop (not an iPad or tablet) that you will be using for work? (Y/N)"
        )
        next_step_in_flow = 'check_computer_response'

    elif current_step_name == 'ask_bilingual':
        message_content = "2. Are you bilingual? (Y/N)"
        next_step_in_flow = 'check_bilingual_response'

    elif current_step_name == 'check_bilingual_response': # This step primarily routes based on collected data
        is_bilingual = state['data'].get('bilingual', False)
        if is_bilingual:
            message_content = "Great! What languages do you speak fluently (besides English, if applicable)?"
            next_step_in_flow = 'ask_languages'
        else:
            message_content = "3. In which state are you located?"
            next_step_in_flow = 'ask_state'

    elif current_step_name == 'ask_languages': # After asking for languages
        message_content = "3. In which state are you located?"
        next_step_in_flow = 'ask_state'

    elif current_step_name == 'ask_state': # After asking for state
        message_content = "4. What is your primary email address?"
        next_step_in_flow = 'ask_email'

    elif current_step_name == 'ask_email' or current_step_name == 'instruct_add_friends': # After asking for email, or if explicitly called
        friends_to_add_list = ["- Adam Black (Support)"]
        if CEO_USER_ID:
            friends_to_add_list.append(f"- {CEO_CONTACT_DISPLAY_NAME}")
        
        friends_to_add_str = "\n".join(friends_to_add_list)
        if not friends_to_add_list:
             friends_to_add_str = "- Adam Black (Support)"

        message_content = (
            "5. Please go into the MAIN CHAT of our Discord server and add the following users as friends:\n"
            f"{friends_to_add_str}\n\n"
            "Have you done this? (Y/N)"
        )
        next_step_in_flow = 'check_add_friends_response'


    elif current_step_name == 'check_add_friends_response': 
        # This step is handled in on_message. If called directly here, it means we want to proceed.
        # on_message will override to provide_training_materials
        pass 

    elif current_step_name == 'provide_training_materials':
        message_content = (
            "6. Next, please complete the following training materials:\n"
            f"   - Read the Training Manual: {TRAINING_MANUAL_URL}\n"
            f"   - Watch the Training Video: {TRAINING_VIDEO_URL}\n"
            f"   - Listen to Training Recordings: {TRAINING_RECORDINGS_URL}\n\n"
            "Once you have completed ALL of these, please reply with 'DONE'."
        )
        next_step_in_flow = 'confirm_training_completion'

    elif current_step_name == 'confirm_training_completion': # After user says DONE
        summary = (
            f"New Hire Onboarding Information for: {user.name} ({user.id})\n"
            f"--------------------------------------------------\n"
            f"Has Computer/Laptop: {'Yes' if state['data'].get('has_computer') else 'No'}\n"
            f"Bilingual: {'Yes' if state['data'].get('bilingual') else 'No'}\n"
        )
        if state['data'].get('languages'):
            summary += f"Languages: {state['data']['languages']}\n"
        summary += (
            f"State: {state['data'].get('state', 'N/A')}\n"
            f"Email: {state['data'].get('email', 'N/A')}\n"
            f"Added Friends: {'Yes' if state['data'].get('added_friends') else 'No, or not confirmed'}\n"
            f"Training Completed: Yes\n"
            f"--------------------------------------------------\n"
            f"This user has completed the initial automated onboarding steps. "
            f"Please verify them and grant access to the main server when ready. "
            f"You can then instruct them to type `complete` in their DM with me to get final instructions."
        )

        successfully_notified_user_facing_names = []
        failed_to_notify_descriptors = []
        state['data']['_notification_attempted'] = False
        state['data']['_successfully_notified_ceo'] = False

        if CEO_USER_ID:
            state['data']['_notification_attempted'] = True

        if CEO_USER_ID:
            ceo_user_to_notify = None
            try:
                ceo_user_to_notify = await client.fetch_user(CEO_USER_ID)
            except discord.NotFound:
                failed_to_notify_descriptors.append(f"{CEO_CONTACT_DISPLAY_NAME} (User ID {CEO_USER_ID} not found)")

            if ceo_user_to_notify:
                try:
                    await ceo_user_to_notify.send(summary)
                    successfully_notified_user_facing_names.append(CEO_CONTACT_DISPLAY_NAME)
                    state['data']['_successfully_notified_ceo'] = True
                    print(f"Successfully sent onboarding summary to {CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID}) for user {user.name}.")
                except discord.Forbidden:
                    failed_to_notify_descriptors.append(f"{CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID} - DMs disabled)")
                except Exception as e:
                    failed_to_notify_descriptors.append(f"{CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID} - Error: {e})")
            elif not any(CEO_CONTACT_DISPLAY_NAME in desc for desc in failed_to_notify_descriptors):
                failed_to_notify_descriptors.append(f"{CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID} - User not fetched)")
        
        next_step_in_flow = 'notify_ceo_and_wait' 

        if successfully_notified_user_facing_names:
            notified_str = " and ".join(successfully_notified_user_facing_names)
            message_content = (
                f"Thank you! I've forwarded your information to {notified_str} for verification.\n"
                f"Please wait for them to contact you or grant you access to the main server channels.\n\n"
                f"Once they have confirmed your verification and you have access, please type `complete` back here in our DM so I can give you your final instructions."
            )
            if failed_to_notify_descriptors: 
                failed_str = ", ".join(failed_to_notify_descriptors)
                message_content += f"\n\nNote: I also encountered issues notifying: {failed_str}. Please ensure they are aware if necessary, or let an admin know."
        elif failed_to_notify_descriptors: 
            failed_str = ", ".join(failed_to_notify_descriptors)
            message_content = (
                f"Thank you for completing the training. I attempted to notify {CEO_CONTACT_DISPLAY_NAME if CEO_USER_ID else 'the designated contact'} but encountered issues: {failed_str}.\n"
                f"Please inform them manually that you'vecompleted this stage. Then type `complete` here once you have confirmation and access."
            )
        else: # No CEO_USER_ID configured
            message_content = (
                "Thank you! Training completion noted. (No CEO ID configured for direct notification via bot).\n"
                "Please inform your hiring manager or supervisor that you have completed this stage.\n"
                "Once they confirm and you have access, type `complete` to proceed to final steps."
            )

    elif current_step_name == 'notify_ceo_and_wait': # User is waiting, no message sent by bot unless prompted by user typing something
        return 

    elif current_step_name == 'final_instructions':
        message_content = (
            "Welcome aboard officially!\n\n"
            "Your final steps are:\n"
            f"1. Please contact {CEO_CONTACT_DISPLAY_NAME} for your next assignments and to get fully integrated.\n"
            "2. Adam Black is your human contact for project specific questions and quality control.\n"
            "3. Samantha is your Discord training and agent support bot on the main server. You can start by telling Samantha that you've finished your onboarding training.\n\n"
            "This concludes your automated onboarding. Good luck!"
        )
        next_step_in_flow = 'completed'

    if message_content:
        try:
            await user.send(message_content)
            if next_step_in_flow: # Only update step if a next step is defined for the message sent
                 user_onboarding_states[user_id]['step'] = next_step_in_flow
                 print(f"User {user.name} advanced to step: {next_step_in_flow}")
            if next_step_in_flow == 'completed':
                print(f"Onboarding completed for user {user.name}. Removing from active states.")
                if user_id in user_onboarding_states:
                    del user_onboarding_states[user_id]
        except discord.Forbidden:
            print(f"Could not send DM to {user.name} ({user_id}). DMs disabled or bot blocked.")
            # Consider removing user from onboarding if DMs are blocked, or have a retry mechanism
        except Exception as e:
            print(f"Error sending DM to {user.name}: {e}")


@client.event
async def on_ready():
    print(f'Logged in as {client.user.name} ({client.user.id})')
    print('------')
    
    notification_targets_log = []
    if CEO_USER_ID:
        notification_targets_log.append(f"{CEO_CONTACT_DISPLAY_NAME} (ID: {CEO_USER_ID})")

    if not notification_targets_log:
        print("WARNING: CEO_USER_ID is not set or valid in .env. CEO notifications for onboarding completion will not be sent by the bot.")
    else:
        print(f"INFO: CEO notifications for onboarding completion will be sent to: {', '.join(notification_targets_log)} (if reachable and configured).")
    
    if DEV_USER_ID:
        print(f"INFO: DEV_USER_ID is set to {DEV_USER_ID} ({ACTUAL_DEV_CONTACT_NAME}). This ID is not currently used for user-facing onboarding notifications.")
    else:
        print("INFO: DEV_USER_ID is not set. (This ID is not currently used for user-facing onboarding notifications).")
    print('------')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if isinstance(message.channel, discord.DMChannel):
        user_id = message.author.id
        processed_message_content = message.content.lower().strip()

        # Handle 'start' command
        if processed_message_content == 'start':
            if user_id not in user_onboarding_states or user_onboarding_states.get(user_id, {}).get('step') == 'completed':
                print(f"Starting onboarding for user {message.author.name} ({user_id}) via 'start' command")
                user_onboarding_states[user_id] = {
                    'step': 'start',
                    'data': {},
                    'dm_channel_id': message.channel.id
                }
                await send_onboarding_message(user_id) # 'start' step will send the first question
            else:
                await message.channel.send("You are already in the onboarding process. Please reply to my last question or type `reset` if you wish to start over.")
            return

        # Handle 'reset' command
        if processed_message_content == 'reset':
            if user_id in user_onboarding_states:
                del user_onboarding_states[user_id]
                await message.channel.send("Your onboarding state has been reset. Type `start` to begin again.")
            else:
                await message.channel.send("You are not currently in an onboarding process to reset.")
            return

        # Handle 'complete' command
        if processed_message_content == 'complete':
            if user_id in user_onboarding_states and user_onboarding_states[user_id]['step'] == 'notify_ceo_and_wait':
                print(f"User {message.author.name} confirmed verification with 'complete'. Proceeding to final instructions.")
                await send_onboarding_message(user_id, step_name_override='final_instructions')
            elif user_id in user_onboarding_states:
                current_user_step = user_onboarding_states[user_id]['step']
                contacts_to_wait_for = []
                
                if user_onboarding_states[user_id]['data'].get('_successfully_notified_ceo'):
                    contacts_to_wait_for.append(CEO_CONTACT_DISPLAY_NAME)
                
                if not contacts_to_wait_for and user_onboarding_states[user_id]['data'].get('_notification_attempted', False) and current_user_step == 'notify_ceo_and_wait':
                     await message.channel.send(f"I attempted to notify {CEO_CONTACT_DISPLAY_NAME if CEO_USER_ID else 'the designated contact'} but couldn't. Please inform them manually, then you can use `complete`.")
                elif contacts_to_wait_for and current_user_step == 'notify_ceo_and_wait':
                    notified_person_descriptor = " and ".join(contacts_to_wait_for)
                    await message.channel.send(f"You can use the `complete` command after {notified_person_descriptor} has confirmed with you and granted access. Please wait for their confirmation.")
                elif not CEO_USER_ID and current_user_step == 'notify_ceo_and_wait':
                    await message.channel.send("You can use `complete` now as no CEO was configured for notification.")
                else: 
                     await message.channel.send(f"You cannot use `complete` at this stage ('{current_user_step}'). Please continue with the current step or wait if you're at the notification stage.")
            else:
                await message.channel.send("You are not currently in an onboarding stage where the `complete` command is applicable.")
            return

        # If user is NOT in onboarding process and didn't type a known command:
        if user_id not in user_onboarding_states:
            await message.channel.send("Hello! To begin the onboarding process, please type `start`.")
            return

        # If user IS in onboarding process, handle their response based on current step:
        if user_id in user_onboarding_states: # Redundant if above check returns, but good for explicit state check
            state = user_onboarding_states[user_id]
            current_step = state['step']
            response = message.content.strip() # Use raw response for data that needs casing/full text

            if current_step == 'check_computer_response':
                if processed_message_content.upper() == 'Y':
                    state['data']['has_computer'] = True
                elif processed_message_content.upper() == 'N':
                    state['data']['has_computer'] = False
                    await message.channel.send(
                        "A computer or laptop (not an iPad or tablet) is required for this role. "
                        "Unfortunately, we cannot proceed with your onboarding at this time without the necessary equipment. "
                        "Please contact your hiring manager if you have any questions or to discuss your situation."
                    )
                    if user_id in user_onboarding_states:
                        del user_onboarding_states[user_id]
                    print(f"Onboarding terminated for user {message.author.name} ({user_id}) due to lack of required equipment.")
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
                # send_onboarding_message will decide next question based on 'bilingual' data
                await send_onboarding_message(user_id, step_name_override='check_bilingual_response') 

            elif current_step == 'ask_languages':
                state['data']['languages'] = response
                # send_onboarding_message for 'ask_languages' will send the 'ask_state' question
                await send_onboarding_message(user_id, step_name_override='ask_languages')

            elif current_step == 'ask_state':
                state['data']['state'] = response 
                normalized_state_input = response.strip().lower()
                if normalized_state_input == 'florida' or normalized_state_input == 'fl':
                    await message.channel.send(
                        "Thank you for your interest. Unfortunately, at this time, we are unable to proceed with your application "
                        "as we do not currently meet the minimum requirements to operate in Florida. We appreciate your understanding."
                    )
                    if user_id in user_onboarding_states: del user_onboarding_states[user_id]
                    print(f"Onboarding process terminated for user {message.author.name} ({user_id}) due to Florida residency.")
                    return
                else:
                    # send_onboarding_message for 'ask_state' will send the 'ask_email' question
                    await send_onboarding_message(user_id, step_name_override='ask_state')

            elif current_step == 'ask_email':
                if re.match(r"[^@]+@[^@]+\.[^@]+", response):
                    state['data']['email'] = response
                    # send_onboarding_message for 'ask_email' will send the 'instruct_add_friends' message
                    await send_onboarding_message(user_id, step_name_override='ask_email') 
                else:
                    await message.channel.send("That doesn't look like a valid email address. Please try again.")
                    return

            elif current_step == 'check_add_friends_response':
                if processed_message_content.upper() == 'Y':
                    state['data']['added_friends'] = True
                elif processed_message_content.upper() == 'N':
                    state['data']['added_friends'] = False
                    friends_to_remind_list = ["Adam Black (Support)"]
                    if CEO_USER_ID:
                        friends_to_remind_list.append(CEO_CONTACT_DISPLAY_NAME)
                    friends_to_remind_str = " and ".join(friends_to_remind_list)
                    if not friends_to_remind_list or (len(friends_to_remind_list)==1 and "Adam Black" in friends_to_remind_list[0] and not CEO_USER_ID):
                        friends_to_remind_str = "Adam Black (Support)"
                    await message.channel.send(f"Please ensure you add {friends_to_remind_str} as friends. This is important for team communication.")
                else:
                    await message.channel.send("Invalid input. Please answer Y or N.")
                    return
                # The 'check_add_friends_response' step in send_onboarding_message has 'pass',
                # so we explicitly move to the next logical step message.
                await send_onboarding_message(user_id, step_name_override='provide_training_materials')

            elif current_step == 'confirm_training_completion':
                if processed_message_content.upper() == 'DONE':
                    state['data']['training_completed'] = True
                    # send_onboarding_message for 'confirm_training_completion' will send summary & notify CEO
                    await send_onboarding_message(user_id, step_name_override='confirm_training_completion') 
                else:
                    await message.channel.send("Please type 'DONE' once you have completed all training materials.")
                    return

            elif current_step == 'notify_ceo_and_wait':
                # User typed something other than 'complete' while in the waiting state
                wait_message = "I've already processed your training completion. "
                contacts_to_wait_for = []
                
                if state['data'].get('_successfully_notified_ceo'):
                    contacts_to_wait_for.append(CEO_CONTACT_DISPLAY_NAME)

                if contacts_to_wait_for:
                    notified_person_descriptor = " and ".join(contacts_to_wait_for)
                    wait_message += (
                        f"Please wait for {notified_person_descriptor} to contact you or grant you access. "
                        "Once they have confirmed and you have access, please type `complete` back here."
                    )
                elif state['data'].get('_notification_attempted'): 
                    wait_message += (
                        f"I attempted to notify {CEO_CONTACT_DISPLAY_NAME if CEO_USER_ID else 'the designated contact'} but encountered issues. "
                        "Please inform them manually that you've completed this stage. "
                        "Then type `complete` here once you have confirmation and access."
                    )
                else: # No CEO configured
                     wait_message += (
                        "Your training completion is noted. As no CEO was configured for notification, "
                        "type `complete` to proceed (this simulates approval)."
                     )
                await message.channel.send(wait_message)
                return

# --- Main Execution ---
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN environment variable not found.")
    else:
        print("Attempting to connect to Discord...")
        try:
            client.run(BOT_TOKEN)
        except discord.LoginFailure:
            print("ERROR: Failed to log in. Check your BOT_TOKEN. It might be invalid or missing.")
        except discord.PrivilegedIntentsRequired:
            print("ERROR: Privileged Intents Required. Please ensure 'SERVER MEMBERS INTENT' and 'MESSAGE CONTENT INTENT' are enabled in your bot's application settings on the Discord Developer Portal.")
        except Exception as e:
            print(f"An unexpected error occurred while trying to run the bot: {e}")