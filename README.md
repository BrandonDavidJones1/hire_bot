# Hire Bot - LTS Onboarding

This project is a Python-based SMS bot designed to walk new hires for "Let's Take Surveys" (LTS) through an initial onboarding process via text messages.

## Features

*   Greets new hires and asks a series of onboarding questions.
*   Collects information such as computer availability, language skills, location, and email.
*   Provides instructions for setting up Discord and completing initial training tasks.
*   Uses Twilio for sending and receiving SMS messages.
*   Built with Flask web framework.

## Setup

### Prerequisites

*   Python 3
*   pip (Python package installer)
*   A Twilio account with an active phone number, Account SID, and Auth Token.
*   `ngrok` for local development to expose the local server to Twilio.

### Local Development

1.  **Clone the repository (if applicable):**
    ```bash
    # git clone <repository_url>
    # cd hire_bot
    ```

2.  **Install dependencies:**
    ```bash
    pip install Flask twilio python-dotenv
    ```

3.  **Environment Variables:**
    Create a `.env` file in the root of the project directory with your Twilio credentials:
    ```env
    TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN=your_auth_token_xxxxxxxxxxxxxx
    TWILIO_PHONE_NUMBER=+12345678900
    ```
    Replace the placeholder values with your actual Twilio Account SID, Auth Token, and Twilio phone number.

4.  **Run ngrok:**
    In a separate terminal, start ngrok to forward a public URL to your local Flask port (default 5000):
    ```bash
    ngrok http 5000
    ```
    Copy the `https://` forwarding URL provided by ngrok.

5.  **Configure Twilio Webhook:**
    *   Go to your Twilio phone number settings in the Twilio console.
    *   Under "Messaging", for "A MESSAGE COMES IN", set the webhook to your ngrok forwarding URL, appending `/sms`.
        *   Example: `https://<your_ngrok_subdomain>.ngrok-free.app/sms`
    *   Ensure the method is HTTP POST.

6.  **Run the Flask Application:**
    In another terminal, start the Python application:
    ```bash
    python app.py
    ```
    The server will start on `http://localhost:5000`.

7.  **Test:**
    Send an SMS message to your Twilio phone number to begin the onboarding flow.
