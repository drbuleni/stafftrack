# StaffTrack

**Staff Accountability & Practice Operations System**

Built for Dr. Buleni's Dental Practice by Vernon Family (Pty) Ltd

---

## Overview

StaffTrack is an internal accountability system designed for professional practices. It solves the behavioral and operational challenges that generic practice management software ignores: staff scheduling transparency, task accountability, performance tracking, and documented compliance.

### What StaffTrack Does

- **Eliminates excuses** - "I didn't know" is no longer valid when tasks, schedules, and SOPs are documented
- **Creates explainability** - When someone's absent, the system shows why (scheduled, on leave, or not scheduled)
- **Provides proof** - Audit logs and performance history create a single source of truth for discipline and recognition
- **Reduces conflict** - Transparent scheduling (especially Saturdays) prevents resentment and confusion

### What StaffTrack Is NOT

- ❌ Not a replacement for clinical software (like GoodX)
- ❌ Not trying to manage patient data
- ❌ Not a complex HR system with 100 features nobody uses

StaffTrack sits in the middle layer: between clinical operations and compliance auditing.

---

## Core Philosophy

> **Simplicity drives adoption. Proof drives accountability. Transparency drives fairness.**

Every feature is designed around actual human behavior in a dental practice, not theoretical "best practices" that get ignored.

---

## MVP Feature Set

### 1. Staff Profiles & Roles

**Staff Member Details:**
- Full name
- Role (Receptionist, Dentist, Dental Assistant, Cleaner, Practice Manager, Super Admin)
- Contact information
- Start date
- Status (Active/Inactive)

**Role-Based Access:**
- Staff see their own data + assigned tasks
- Practice Manager sees team performance
- Super Admin sees everything + audit logs

### 2. Digital Receipts & Cash Reconciliation

**Receipt Creation:**
- Receipt number (auto-generated)
- Date
- Amount
- Payment method (Cash/Card/EFT)
- Description
- Created by (auto-logged)

**Daily Cash Summary:**
- Total receipts for the day
- Cash receipts specifically
- Physical cash counted
- Discrepancy alert if mismatch

**Permissions:**
- Only Receptionist, Practice Manager, and Doctor can create receipts
- All entries are audit-logged

### 3. Task Management

**Task Structure:**
- Task name
- Description (optional)
- Assigned to (staff member)
- Due date (optional)
- Status: To Do → In Progress → Done
- Created by + date

**Staff View:**
- "My Tasks" dashboard
- Clear list of responsibilities
- Cannot claim "I didn't know"

**Manager View:**
- Overdue tasks highlighted
- Completion patterns by staff member
- Feeds into KPI scoring automatically

### 4. Staff Scheduling

**Scheduling Logic:**
- Monthly calendar view
- Focus on Saturdays (high-conflict days)
- Assign: Staff member + Role + Date

**Smart Behavior:**
- Staff on approved leave → Cannot be scheduled (system blocks it)
- Scheduled → Shows "Working"
- Not scheduled → Shows "Off"
- Everyone sees the same schedule (no WhatsApp confusion)

**Result:** Transparent, fair, no misunderstandings.

### 5. Leave Management

**Leave Request:**
- Staff member submits: Leave type + Start date + End date + Reason
- Status: Pending → Approved/Rejected

**Manager Approval:**
- Practice Manager or Doctor approves/rejects
- System shows reason for rejection if denied

**Integration with Scheduling:**
- Approved leave blocks scheduling automatically
- Absence explanation always visible

### 6. KPI Scoring System

**Scoring Logic (Simple = Usable):**

Each KPI is binary:
- ✅ Met = 1 point
- ❌ Not Met = 0 points

**Example KPIs:**
- Bathrooms always clean
- Sterilization completed properly
- Waste disposed correctly
- Tasks completed on time
- On time for shifts

**Weekly/Monthly Scoring:**
- System auto-totals points
- Converts to percentage
- Ranks employees
- Identifies Employee of the Week/Month automatically

**Staff View:**
- Can see their own scores
- Understand where they're falling short

**Manager View:**
- Compare performance across team
- Spot patterns (who's consistent, who's slipping)

### 7. Performance History Timeline

**Each employee has a timeline showing:**
- KPI scores (weekly/monthly)
- Tasks completed vs missed
- Leave taken
- Warnings issued
- Recognition received

**This becomes the single source of truth.**

When discipline happens, it's backed by data - not feelings or bias.

### 8. Training & SOP Acknowledgement

**Document Upload:**
- Upload policy/SOP/training document
- Version tracking

**Staff Acknowledgement:**
- Staff clicks "Read" and "I Understand"
- System records: Name + Date + Document Version

**Legal Shield:**
> "I didn't know about this policy" is no longer a valid defense.

**Use Cases:**
- OHSC compliance requirements
- COVID protocols
- Cash handling procedures
- Sterilization standards

### 9. Warning & Escalation Automation

**Automated Triggers:**
- 3 late arrivals → Warning issued
- 2 consecutive failed KPI weeks → Performance flag
- Repeated missed tasks → Escalation

**Transparency:**
- Staff can see their own warning count
- No surprises
- No bias

**Manager Control:**
- Can manually issue warnings with reason
- System tracks all warnings in performance history

**Result:** Fair, transparent, documented discipline process.

### 10. Audit Log

**What Gets Logged:**
- Receipt creation/edits
- Leave approvals/rejections
- KPI score entries
- Warning issuances
- SOP acknowledgements
- Schedule changes

**Visibility:**
- Super Admin only
- Immutable record (cannot be edited)

**Protection For:**
- The business (legal disputes)
- The system builder (proof of integrity)
- Dr. Buleni (operational proof)

---

## User Roles & Permissions

### Staff Member
- View own profile
- View own tasks
- View own KPI scores
- Submit leave requests
- Acknowledge SOPs
- View schedule

### Receptionist
- All Staff Member permissions
- Create digital receipts
- View daily cash summary
- Reconcile cash

### Dental Assistant / Dentist
- All Staff Member permissions
- (No additional permissions in MVP)

### Practice Manager
- All Staff Member permissions
- Create/assign tasks
- Approve/reject leave
- Score KPIs
- View team performance
- Issue warnings
- Manage schedule
- View all staff data

### Super Admin (Dr. Buleni)
- All permissions
- View audit logs
- Manage user accounts
- System configuration
- Final approval authority

---

## Technical Architecture

### Technology Stack (Recommended)

**Backend:**
- Python with Flask (lightweight, fast to build)
- SQLite for MVP (can migrate to PostgreSQL later)
- SQLAlchemy ORM

**Frontend:**
- HTML/CSS/JavaScript
- Bootstrap for responsive design
- Minimal JavaScript frameworks (keep it simple)

**Authentication:**
- Flask-Login for session management
- Password hashing with bcrypt
- Role-based access control

**File Storage:**
- Local filesystem for SOP documents (MVP)
- Can move to cloud storage later

### Database Schema (Core Tables)

**users**
- id, username, password_hash, full_name, role, email, phone, start_date, status, created_at

**receipts**
- id, receipt_number, date, amount, payment_method, description, created_by, created_at

**tasks**
- id, title, description, assigned_to, due_date, status, created_by, created_at, updated_at

**schedule**
- id, staff_id, date, role, created_by, created_at

**leave_requests**
- id, staff_id, leave_type, start_date, end_date, reason, status, approved_by, approved_at, created_at

**kpi_scores**
- id, staff_id, week_start_date, kpi_category, score (0 or 1), scored_by, scored_at

**performance_history**
- id, staff_id, event_type, event_data, created_at

**sop_documents**
- id, title, file_path, version, uploaded_by, uploaded_at

**sop_acknowledgements**
- id, sop_id, staff_id, acknowledged_at

**warnings**
- id, staff_id, warning_type, reason, issued_by, issued_at

**audit_log**
- id, user_id, action, entity_type, entity_id, details, ip_address, created_at

---

## Development Phases

### Phase 1: MVP (Build This First)
- Staff profiles & roles
- Digital receipts + cash reconciliation
- Task management
- Staff scheduling
- Leave management
- KPI scoring
- Performance history
- Training & SOP acknowledgement
- Warning automation
- Audit log

### Phase 2: Enhancements (After MVP Validation)
- Email/SMS notifications
- Mobile-responsive improvements
- Advanced reporting/analytics
- Export to PDF/Excel
- Integration with GoodX (if needed)
- Multi-practice support
- Cloud deployment

### Phase 3: Productization (If Expanding)
- SaaS pricing model
- Multi-tenant architecture
- Onboarding automation
- Customer success tracking
- Marketing site

---

## Design Principles

1. **Minimal Friction** - If a feature adds steps, question whether it's needed
2. **One Source of Truth** - Never have conflicting information in multiple places
3. **Role-Appropriate Views** - Show people only what they need to see
4. **Audit Everything** - If it matters for accountability, log it
5. **No Opinions, Just Facts** - The system shows data, not judgments

---

## Success Metrics

**For Dr. Buleni:**
- Reduced scheduling conflicts
- Fewer "I didn't know" excuses
- Clear performance data for staff reviews
- Legal protection from documented policies
- Time saved on admin overhead

**For Staff:**
- No confusion about expectations
- Fair, transparent performance tracking
- Clear view of own responsibilities
- Reduced workplace conflict

---

## Future Expansion Potential

While built for Dr. Buleni's dental practice, this architecture applies to:
- Medical practices
- Law firms
- Accounting firms
- Any professional service with staff accountability challenges

The "internal accountability layer" is currently underserved in most practice management software.

---

## Contact

**Built by:** Vernon Family (Pty) Ltd  
**For:** Dr. Buleni's Dental Practice  
**Developer:** Vernon  
**Version:** 1.0.0 MVP  
**Last Updated:** January 2026

---

## License

Proprietary software developed for Dr. Buleni's Dental Practice.
