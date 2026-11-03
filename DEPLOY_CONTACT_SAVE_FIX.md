# Deploy Contact Info Save Fix

## Issue Fixed
AI was repeatedly asking for address, city, and zip code even after user provided them, and booking was not being created because contact information wasn't being saved to the session.

## Solution Implemented
Created `save_booking_contact` tool that allows the AI to save contact information (address, city, zip code) when the user provides it in the chat conversation.

## Changes Made

### 1. app/agent/tools.py
- **Added new tool**: `save_booking_contact(address, city, zip_code, session_id)`
  - Saves contact information to session.booking_contact
  - Validates that session_id matches current session
  - Returns confirmation message to AI
- **Registered in TOOLS dictionary** at the end of the file

### 2. app/agent/assistant.py
- **Updated system prompt** with instruction:
  ```
  When user provides contact details (address, city, zip code) in the conversation:
  - IMMEDIATELY call save_booking_contact tool with the provided information
  - Parse the information correctly (e.g., "P4 1202 prateek grand noida 128017" → address="P4 1202 prateek grand noida", city="noida", zip_code="128017")
  - Confirm the information was saved
  - Then proceed with payment
  ```

## Git Status
- **Branch**: fixes
- **Latest Commit**: a72bcc7 "Add save_booking_contact tool to fix repeated address/contact asking issue"
- **Status**: Committed locally, needs to be pushed

## Deployment Steps

### Step 1: Push Changes (if not already done)
```bash
cd /path/to/local/repo/a-agent-base
git push origin fixes
```

### Step 2: Deploy on Server
```bash
# SSH into the server
ssh ubuntu@172.31.32.142

# Navigate to the correct directory
cd /var/www/a-agent-base

# Pull the latest changes
git pull origin fixes

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# Restart the PM2 service
pm2 restart agentserver

# Check if service is running
pm2 status

# Monitor logs for any errors
pm2 logs agentserver --lines 50
```

## Verification Steps

### Test Case: User provides complete address in chat
1. Start a booking conversation
2. Select a service
3. Choose appointment time
4. Select "Home Service" for appointment location
5. Select "Individual" booking type
6. Choose payment method (PayNow or PayAtSalon)
7. **Provide address in chat**: "P4 1202 prateek grand noida 128017"

### Expected Behavior:
- ✅ AI should call `save_booking_contact` tool immediately
- ✅ Tool saves: address="P4 1202 prateek grand noida", city="noida", zip_code="128017"
- ✅ AI confirms information was saved
- ✅ AI should NOT ask for address/city/zip again
- ✅ AI proceeds directly to create booking
- ✅ Booking is created successfully with contact info

### Check Logs:
```bash
# On server, monitor PM2 logs
pm2 logs agentserver --lines 100

# Look for:
# - "save_booking_contact called with session_id=..."
# - "Contact info saved successfully"
# - No repeated prompts for address
```

## Rollback Plan (if needed)
```bash
# On server
cd /var/www/a-agent-base
git log --oneline -5  # Find previous commit hash
git checkout <previous-commit-hash>
pm2 restart agentserver
```

Previous stable commit: `5322964` (Fix syntax error: longitude missing .longitude attribute)

## Technical Details

### New Tool Schema
```python
def save_booking_contact(address: str, city: str, zip_code: str, session_id: str):
    """
    Save user's contact information (address, city, zip code) to the booking session.
    
    Args:
        address: Street address
        city: City name
        zip_code: Postal/ZIP code
        session_id: Current session ID for validation
    
    Returns:
        Confirmation message
    """
```

### Session Storage
Contact info is saved to: `session.booking_contact` dictionary
```python
{
    "address": "P4 1202 prateek grand noida",
    "city": "noida",
    "zip_code": "128017",
    "booking_appointment": "Home"  # or "Salon"
}
```

### Integration with Booking Flow
When `confirm_booking` is called, it reads from `session.booking_contact` to populate the booking payload. With this fix, the contact info will already be saved, so validation will pass and booking will be created.

## Related Issues Fixed Previously
1. ✅ Payment flow shows immediate confirmation (no "salon will review")
2. ✅ Address requirements based on Salon vs Home service
3. ✅ Individual/Group booking type selection
4. ✅ Salon Visit/Home Service location choice
5. ✅ Syntax error line 664 (longitude attribute)
6. ✅ **NEW**: Save contact info from chat to prevent repeated asking

## Contact
If any issues occur during deployment, check:
1. PM2 logs: `pm2 logs agentserver`
2. Git status: `git status` and `git log`
3. Python cache cleared: `find . -name __pycache__ | wc -l` (should be 0)
4. Correct directory: `pwd` should show `/var/www/a-agent-base`

---
**Deployment Date**: To be deployed after push completes
**Deployed By**: TBD
**Status**: Ready for deployment
