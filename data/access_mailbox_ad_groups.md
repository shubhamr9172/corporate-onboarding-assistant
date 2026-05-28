# Corporate Onboarding: Shared Mailboxes & Active Directory Groups

This document outlines how to request membership in Active Directory (AD) security groups and gain access to shared/group mailboxes.

## 1. Active Directory (AD) Security Groups
Active Directory groups control access to network file shares, SharePoint sites, distribution lists, and local computer administrative privileges.

### A. How to Find Your Required AD Groups
To find the AD groups assigned to your peers or those required for your role, consult your Line Manager. Common group types include:
- `DL-Dept-*`: Distribution Lists for department emails (e.g., `DL-Dept-Engineering`).
- `SG-App-*`: Security Groups granting application access (e.g., `SG-App-JiraUsers`).
- `SG-FS-*`: File Share permission groups (e.g., `SG-FS-Finance-ReadWrite`).

### B. Requesting AD Group Membership
1. Open the **SailPoint Identity Portal** or the internal identity manager.
2. Select **Request Group Membership**.
3. Search for the specific AD Group name (e.g., `SG-App-Github-Developers`).
4. Enter a detailed business justification.
5. Submit the request.
- **Approval Flow**: The system automatically routes the request to the designated **Group Owner** for approval. Most requests are processed within 2 hours of approval.

---

## 2. Shared Mailbox Access
Shared mailboxes (e.g., `info@corporate.com`, `support@corporate.com`, `eng-alerts@corporate.com`) allow multiple users to view and send email from a common email address.

### A. Requesting Access
- **Prerequisite**: You must have an active corporate Exchange/O365 account.
- **Request Platform**: ServiceNow Portal -> "Request Access to Shared Mailbox"
- **Required Fields**:
  - Email address of the shared mailbox.
  - Required permissions:
    - **Read and Write**: Access to read emails and send responses *as* the mailbox.
    - **Send on Behalf**: Send emails from your personal account that show as "Sent on behalf of [Mailbox]".
    - **Read-Only**: Read and monitor emails only.
- **Approval Flow**: Approved by the designated Mailbox Custodian (usually the team lead or manager associated with the mailbox).

### B. Accessing the Mailbox in Microsoft Outlook
Once access is granted:
- **Outlook Web App (OWA)**: Click your profile picture in the top right -> **Open another mailbox** -> Type the shared mailbox address.
- **Outlook Desktop (Windows/Mac)**: The shared mailbox will automatically appear in your folder list sidebar within 12-24 hours after restarting Outlook. If it does not appear, you can add it manually via **Account Settings -> Double-click account -> More Settings -> Advanced -> Add (Open these additional mailboxes)**.
