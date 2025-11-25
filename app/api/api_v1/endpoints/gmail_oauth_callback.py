"""
Gmail OAuth callback endpoint for seamless web-based OAuth flow.

Handles OAuth callback from Google and redirects back to dashboard.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_v1 import deps
from app.services.gmail_service import GmailService
from app.services.auth.credential_manager import credential_manager
from app.models.user import CredentialType

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/oauth/callback")
async def gmail_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None, description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="OAuth state parameter"),
    error: Optional[str] = Query(None, description="OAuth error"),
    error_description: Optional[str] = Query(None, description="Error description"),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Handle Gmail OAuth callback from Google.

    This endpoint receives the authorization code from Google,
    exchanges it for credentials, and redirects back to dashboard.
    """
    try:
        # Handle OAuth errors
        if error:
            logger.error(f"Gmail OAuth error: {error} - {error_description}")
            # Redirect to dashboard with error
            return RedirectResponse(
                url=f"http://localhost:3000/auth/gmail/error?error={error}&description={error_description}"
            )

        if not code:
            logger.error("No authorization code received from Google")
            return RedirectResponse(
                url="http://localhost:3000/auth/gmail/error?error=no_code&description=No+authorization+code"
            )

        logger.info(f"Received Gmail OAuth callback with state: {state}")

        try:
            # Exchange authorization code for credentials
            gmail_service = GmailService()
            credentials = await gmail_service.exchange_code_for_credentials(
                authorization_code=code,
                redirect_uri="http://localhost:8000/api/v1/gmail/oauth/callback"
            )

            # Build service to validate credentials and get user info
            await gmail_service.build_service(credentials)
            user_info = await gmail_service.get_user_info()

            email_address = user_info.get("email_address")
            
            # Extract user_id from state parameter
            user_id = None
            if state:
                try:
                    state_parts = state.split(':')
                    if len(state_parts) >= 2:
                        user_id = state_parts[1]
                except Exception:
                    logger.warning(f"Could not extract user_id from state: {state}")
            
            if not user_id:
                logger.error("No user_id found in state parameter")
                return RedirectResponse(
                    url="http://localhost:3000/auth/gmail/error?error=no_user_id&description=Missing+user+ID+in+state"
                )

            # Store credentials securely in database
            credential_data = {
                "token": credentials.get("token"),
                "refresh_token": credentials.get("refresh_token"),
                "token_uri": credentials.get("token_uri"),
                "client_id": credentials.get("client_id"),
                "client_secret": credentials.get("client_secret"),
                "scopes": credentials.get("scopes", []),
                "email": email_address,
                "user_info": user_info
            }

            # Set expiration (Gmail tokens typically expire in 1 hour)
            from datetime import datetime, timedelta, timezone
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

            # Store in database using credential manager
            success = await credential_manager.store_credentials(
                db=db,
                user_id=user_id,
                credential_type=CredentialType.GMAIL_OAUTH,
                credentials=credential_data,
                expires_at=expires_at,
                metadata={
                    "email": email_address,
                    "state": state,
                    "user_info": user_info
                }
            )

            if not success:
                logger.error(f"Failed to store Gmail credentials for user {user_id}")
                return RedirectResponse(
                    url=f"http://localhost:3000/auth/gmail/error?error=storage_failed&description=Failed+to+store+credentials"
                )

            logger.info(f"Successfully stored Gmail credentials for user {user_id} ({email_address})")

            # Redirect to dashboard with success
            return RedirectResponse(
                url=f"http://localhost:3000/auth/gmail/success?"
                f"email={email_address}&"
                f"state={state}&"
                f"message=Gmail+successfully+connected"
            )

        except Exception as e:
            logger.error(f"Failed to exchange authorization code: {str(e)}")
            return RedirectResponse(
                url=f"http://localhost:3000/auth/gmail/error?error=exchange_failed&description={str(e)}"
            )

    except Exception as e:
        logger.error(f"Unexpected error in OAuth callback: {str(e)}")
        return RedirectResponse(
            url=f"http://localhost:3000/auth/gmail/error?error=unexpected&description={str(e)}"
        )


@router.get("/auth/quick")
async def quick_gmail_auth(
    request: Request,
    user_id: str = Query(..., description="User ID"),
    redirect_to: str = Query("http://localhost:3000/dashboard", description="Where to redirect after auth")
):
    """
    Quick Gmail OAuth authorization - one-click flow.

    This generates the authorization URL and immediately redirects the user.
    """
    try:
        gmail_service = GmailService()
        authorization_url, state = await gmail_service.get_authorization_url(
            redirect_uri="http://localhost:8000/api/v1/gmail/oauth/callback",
            state=f"user_id:{user_id}:redirect_to:{redirect_to}"
        )

        logger.info(f"Generated quick Gmail auth URL for user {user_id}")

        # Immediately redirect to Google OAuth
        return RedirectResponse(url=authorization_url)

    except Exception as e:
        logger.error(f"Failed to generate quick auth URL: {str(e)}")
        # Redirect back with error
        return RedirectResponse(
            url=f"{redirect_to}?error=auth_failed&description={str(e)}"
        )