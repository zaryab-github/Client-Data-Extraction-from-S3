                                ┌───────────────────┐
                                │       USER        │
                                └─────────┬─────────┘
                                          │
                                          ▼
                                ┌───────────────────┐
                                │  FRONTEND PORTAL  │
                                │                   │
                                │ Login             │
                                │ Dashboard         │
                                │ Shortcode Select  │
                                │ Date/Time Range   │
                                │ Generate Report   │
                                │ Job Status        │
                                │ Download ZIP      │
                                │ Email Report      │
                                │ Extraction History│
                                │ Optional AI       │
                                └─────────┬─────────┘
                                          │
                                          │ HTTPS / REST API
                                          ▼
                                ┌───────────────────┐
                                │   FASTAPI BACKEND │
                                │                   │
                                │ Authentication    │
                                │ Authorization     │
                                │ RBAC              │
                                │ Shortcode Access │
                                │ Extraction API    │
                                │ Job API           │
                                │ Download API      │
                                │ Email API         │
                                │ Audit Logging     │
                                └───────┬─────┬──────┘
                                        │     │
                         ┌──────────────┘     └──────────────┐
                         ▼                                   ▼
                ┌─────────────────┐                 ┌─────────────────┐
                │  APPLICATION DB │                 │      REDIS      │
                │                 │                 │                 │
                │ Users           │                 │ Celery Broker   │
                │ Roles           │                 │ Job Queue       │
                │ Shortcodes      │                 └────────┬────────┘
                │ Permissions    │                          │
                │ Job Metadata   │                          ▼
                │ Report Metadata│                 ┌─────────────────┐
                │ Audit Logs     │                 │ CELERY WORKER   │
                └─────────────────┘                 │                 │
                                                    │ Extraction Job  │
                                                    │ CSV Processing  │
                                                    │ ZIP Creation    │
                                                    └────────┬────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │     AWS S3       │
                                                    │                 │
                                                    │ Daily CSV Files │
                                                    │ Client Data     │
                                                    └────────┬────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │ EXTRACTION ENGINE│
                                                    │                 │
                                                    │ Find CSV Files  │
                                                    │ Read CSVs       │
                                                    │ Filter Shortcode│
                                                    │ Filter Date/Time│
                                                    │ Combine Records │
                                                    │ Generate CSV    │
                                                    │ Create ZIP      │
                                                    └────────┬────────┘
                                                             │
                                                             ▼
                                             ┌──────────────────────────┐
                                             │ LOCAL APPLICATION STORAGE│
                                             │                          │
                                             │ Job ID Directory         │
                                             │ Generated CSV            │
                                             │ Generated ZIP            │
                                             │ Job Metadata             │
                                             └────────────┬─────────────┘
                                                          │
                                       ┌──────────────────┴─────────────────┐
                                       ▼                                    ▼
                              ┌─────────────────┐                  ┌─────────────────┐
                              │ DOWNLOAD ZIP    │                  │ EMAIL DELIVERY  │
                              │                 │                  │                 │
                              │ User Downloads  │                  │ AWS SES / SMTP  │
                              │ Generated File  │                  │ Attachment/Link│
                              └─────────────────┘                  └─────────────────┘


1. Project Overview
    Build a secure web-based application that allows authenticated users to extract client-specific data from multiple daily CSV files stored in an AWS S3 bucket.
    Each CSV file contains data for multiple clients. Client records are identified by a unique shortcode.
    Users can log in to the portal, select one or more authorized shortcodes, define a date/time range, and request a data extraction.


The system will:
    Authenticate the user.
    Validate the user's shortcode permissions.
    Identify relevant CSV files in S3.
    Process multiple CSV files.
    Filter records by shortcode and date/time.
    Combine matching records.
    Generate a new CSV file.
    Generate a ZIP archive containing the CSV.
    Assign a unique Job ID.
    Store the generated ZIP and metadata in configurable local application storage.
    Allow the user to download the ZIP.
    Optionally send the report by email.
    Maintain extraction history and audit logs.

    The actual client data remains in AWS S3 CSV files.

The application database stores only application metadata, not the client CSV data.




2. Detailed Data Flow
User
 │
 │ Login
 ▼
Frontend
 │
 │ Select:
 │ - Shortcode(s)
 │ - Start Date/Time
 │ - End Date/Time
 │ - Email Option
 ▼
FastAPI
 │
 │ Authenticate
 │ Check RBAC
 │ Check Shortcode Permission
 ▼
Create Job ID
 │
 ▼
Database
 │
 │ Status = PENDING
 ▼
Redis
 │
 ▼
Celery Worker
 │
 ▼
Find Relevant S3 CSV Files
 │
 ▼
Process Multiple CSV Files
 │
 ├── CSV 1
 ├── CSV 2
 ├── CSV 3
 ├── CSV 4
 └── ...
 │
 ▼
Filter by Shortcode
 │
 ▼
Filter by Date/Time
 │
 ▼
Combine Matching Records
 │
 ▼
Generate New CSV
 │
 ▼
Create ZIP
 │
 ▼
Save:
 │
 ├── CSV
 ├── ZIP
 └── Metadata
 │
 ▼
Local Application Storage
 │
 ▼
Update Database
 │
 Status = COMPLETED
 │
 ├───────────────┐
 ▼               ▼
Download        Email