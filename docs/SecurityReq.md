# Security Requirements & Standards

## Introduction

### Overview
GHCP Usage Dashboard is a local-only tool with a minimal attack surface. Security requirements are driven by the principle of **data locality** — no usage data leaves the developer's machine unless the user explicitly configures GitHub API integration.

### Scope
This document covers security requirements for:
- Local data storage (SQLite database)
- HTTP dashboard server (localhost binding)
- GitHub API token handling (optional)
- Input parsing (JSONL log files)

### Security Philosophy
**Privacy by default. Security by simplicity.**
- No external network calls unless explicitly configured
- No authentication on localhost (trust the local user)
- No persistent credentials on disk
- Minimal code surface to audit

### Audience
Developers evaluating the tool for corporate use, security reviewers, and contributors.

### Regulatory Context
- GDPR: Compliant by architecture (no data transmission, no external processing)
- SOC 2: No shared infrastructure to audit
- Corporate IT: Zero-install, no elevated privileges required

### Last Updated
April 2026 (v0.1)

## Security Strategy & Framework

### Security Objectives
1. **Confidentiality**: Usage data is accessible only to the local user
2. **Integrity**: Database records are not tampered with during scan/read cycles
3. **Availability**: Tool functions without network access (except optional API integration)

### Security Principles
1. **Least Privilege**: No elevated permissions required. Reads only from VS Code log directories.
2. **Defense in Depth**: Parameterized SQL, XSS escaping, localhost binding, input validation.
3. **Fail Secure**: Malformed log lines are skipped (not executed). Parse errors don't corrupt the database.

### Threat Model Overview

| Threat | Likelihood | Impact | Mitigation |
|--------|-----------|--------|------------|
| SQL injection via crafted log file | Low | High | Parameterized queries (`?` placeholders) — never string concatenation |
| XSS via project name in dashboard | Medium | Medium | `esc()` function creates text nodes for all dynamic content |
| Unauthorized network access to dashboard | Low | Medium | Bind to `localhost` by default; `HOST` override requires explicit env var |
| GitHub token exposure | Medium | High | Token stored in env var only; never logged, never written to DB or files |
| Malicious log file causing DoS | Low | Low | Per-line parsing with try/except; corrupted files are skipped |
| Data exfiltration via Chart.js CDN | Very Low | Low | CDN request is GET-only for a JS file; no data sent. Optional: bundle locally. |

### Risk Assessment Approach
- Threat modeling performed using STRIDE methodology
- Focus on local attack vectors (crafted log files, environment manipulation)
- Remote attack vectors are minimal (localhost-only server)

## Authentication Requirements

### User Authentication
- **Not applicable**: Local tool, no user accounts, no login
- The operating system's file permissions protect the database and log files

### Service-to-Service Authentication
#### GitHub API Token (v0.2)
- **Type**: Personal Access Token (PAT) or fine-grained token
- **Scope required**: `copilot` (read-only)
- **Storage**: Environment variable `GITHUB_TOKEN`
- **Transmission**: HTTPS only, `Authorization: Bearer` header
- **Never stored in**: Config files, database, log output, error messages

### Session Management
- **Not applicable**: No user sessions. Dashboard is stateless.
- HTTP server does not set cookies or maintain server-side session state.

## Data Protection Requirements

### Data at Rest
| Data | Location | Protection |
|------|----------|-----------|
| SQLite database | `~/.ghcp-usage/usage.db` | OS file permissions (user-only read/write) |
| Copilot log files | VS Code extension directory | OS file permissions (read by scanner) |
| GitHub API token | Environment variable | Not written to disk by the tool |

- **Encryption**: Not implemented (local file, protected by OS). Users in high-security environments should use full-disk encryption.
- **Database file permissions**: Created with default umask (typically `0644` on Unix). Documentation recommends `chmod 600` for sensitive environments.

### Data in Transit
| Channel | Encryption | Details |
|---------|-----------|---------|
| Dashboard (localhost) | None | HTTP on localhost — no network transit |
| GitHub API calls | TLS 1.2+ | HTTPS via `urllib.request` |
| Chart.js CDN | TLS 1.2+ | HTTPS GET request to jsdelivr.net |

### Data Retention
- **No automatic deletion**: Data persists until user runs `--reset` or manually deletes the database
- **No data expiry**: All historical data is kept
- **User controls**: `python cli.py scan --reset` drops all data and rescans

## Input Validation & Injection Prevention

### JSONL Parsing
- Each line parsed independently with `json.loads()` — never `eval()` or `exec()`
- Malformed JSON lines are caught with `try/except` and skipped
- No shell command construction from log data
- File paths from logs are stored as strings, never executed

### SQL Injection Prevention
- **All queries use parameterized placeholders** (`?`)
- Example: `conn.execute("SELECT * FROM turns WHERE session_id = ?", (session_id,))`
- **No string formatting or f-strings in SQL queries**
- Schema creation uses `executescript()` with static SQL only

### XSS Prevention (Dashboard)
- All dynamic content rendered via `esc()` function:
  ```javascript
  function esc(s) {
      const d = document.createElement('div');
      d.textContent = String(s);
      return d.innerHTML;
  }
  ```
- No `innerHTML` with unescaped user data
- No `eval()` or `Function()` in dashboard JavaScript

### Path Traversal Prevention
- Log directory paths are validated with `pathlib.Path.resolve()`
- Scanner only reads files matching `*.jsonl` / `*.log` globs
- No file writes outside the database path

## Network Security

### Dashboard Server
- **Default bind**: `localhost` (127.0.0.1) — not accessible from other machines
- **Override**: `HOST=0.0.0.0` exposes to network — **user must explicitly opt in**
- **No TLS**: Localhost HTTP is acceptable per security best practices (no network transit)
- **No CORS headers**: Same-origin only
- **No authentication**: Relies on localhost binding for access control

### Outbound Connections
| Destination | Purpose | Required? |
|-------------|---------|-----------|
| `cdn.jsdelivr.net` | Chart.js library | Yes (first load, then browser-cached) |
| `api.github.com` | Org usage metrics | No (opt-in, v0.2) |

### Firewall Considerations
- Tool works fully offline except for Chart.js CDN (can be pre-cached)
- No inbound connections required
- No listening ports except localhost:8080 (configurable)

## Dependency Security

### Runtime Dependencies
- **Zero third-party packages**: Only Python standard library
- No supply chain risk from PyPI packages
- No `requirements.txt` to audit

### Development Dependencies (optional)
- `pytest`: Testing only, well-established, MIT licensed
- `ruff` / `black`: Linting/formatting only, not shipped

### CDN Dependency
- Chart.js loaded from `cdn.jsdelivr.net` with pinned version (`4.4.0`)
- **Mitigation for CDN compromise**: Consider adding Subresource Integrity (SRI) hash
- **Offline alternative**: Bundle `chart.umd.min.js` locally

## Security Checklist (OWASP Top 10 Mapping)

| OWASP Category | Risk Level | Mitigation |
|---------------|-----------|------------|
| A01: Broken Access Control | Low | Localhost binding, OS file permissions |
| A02: Cryptographic Failures | N/A | No encryption needed (local data, no secrets stored) |
| A03: Injection | Low | Parameterized SQL, `json.loads()` parsing |
| A04: Insecure Design | Low | Minimal attack surface, local-only architecture |
| A05: Security Misconfiguration | Low | Secure defaults (localhost, no debug mode) |
| A06: Vulnerable Components | Very Low | Zero third-party runtime dependencies |
| A07: Auth Failures | N/A | No authentication system |
| A08: Data Integrity Failures | Low | No deserialization of untrusted objects |
| A09: Logging Failures | Low | Scanner logs parse errors; no sensitive data in logs |
| A10: SSRF | Low | No server-side URL fetching from user input |

### Password Reset/Recovery
#### Reset Link Expiration
#### Verification Requirements
#### Recovery Questions
#### Email Verification

### Remember Me Functionality
#### Cookie Security
#### Token Generation
#### Token Expiration
#### Renewal Logic

## Authorization & Access Control

### Role-Based Access Control (RBAC)
#### Defined Roles
#### Role Permissions
#### Role Assignment
#### Role Hierarchy

### Attribute-Based Access Control (ABAC)
#### Attributes Considered
#### Policy Evaluation
#### Dynamic Access Control

### Resource-Level Authorization
#### Resource Ownership
#### Shared Resource Access
#### Permission Inheritance
#### Default Permissions

### API Authorization
#### Endpoint-Level Authorization
#### Method-Level Authorization
#### Resource-Level Authorization
#### Scope-Based Authorization

### Administrative Access
#### Admin Role Requirements
#### Admin Activity Logging
#### Admin Tool Access
#### Privilege Escalation Prevention

### Data Access Control
#### User's Own Data Access
#### Cross-User Data Restriction
#### Bulk Data Access Restrictions
#### Data Export Restrictions

## Encryption Requirements

### Data at Rest
#### Encryption Algorithm
#### Encryption Standard (AES-256)
#### Key Management
#### Key Rotation Frequency
#### Sensitive Data Classification

### Data in Transit
#### TLS Version Requirement
#### TLS Version Minimum
#### Cipher Suite Requirements
#### Certificate Requirements
#### SSL/TLS Enforcement

### API Communication
#### HTTPS Requirement
#### Certificate Validation
#### Certificate Pinning
#### Certificate Expiration Monitoring

### Database Encryption
#### Transparent Data Encryption (TDE)
#### Column-Level Encryption
#### Backup Encryption
#### Key Management

### File/Backup Encryption
#### Encryption Method
#### Key Storage
#### Key Rotation
#### Decryption Process

## Data Protection & Privacy

### Data Classification
#### Public Data
#### Internal Data
#### Confidential Data
#### Restricted Data

### PII (Personally Identifiable Information)
#### PII Definition
#### PII Identification
#### PII Protection Requirements
#### PII Minimization

### Sensitive Data Handling
#### Passwords: Never Store in Plaintext
#### Tokens: Hash Before Storage
#### Credit Cards: PCI-DSS Compliance
#### Health Data: HIPAA Compliance

### Data Retention Policy
#### Retention by Data Type
#### Deletion Process
#### Archive Strategy
#### Legal Hold

### Data Export & Sharing
#### Export Controls
#### Approval Process
#### Data Masking Requirements
#### Audit Logging

### Right to Be Forgotten (GDPR)
#### User Data Deletion
#### Data Anonymization
#### Deletion Deadline
#### Verification

## Compliance & Regulatory Requirements

### GDPR Compliance
#### Data Processing Agreement
#### Privacy Policy Requirements
#### User Consent Management
#### Data Subject Rights
#### Breach Notification (72 hours)

### HIPAA Compliance (if applicable)
#### Privacy Rule
#### Security Rule
#### Breach Notification Rule

### PCI-DSS Compliance (if processing cards)
#### Card Data Handling
#### Encryption Requirements
#### Tokenization
#### Compliance Audits

### CCPA/CPRA Compliance
#### Consumer Rights
#### Opt-Out Mechanisms
#### Data Selling Restrictions

### SOC 2 Compliance
#### Type I Audit
#### Type II Audit
#### Compliance Certification

### ISO 27001 Compliance
#### Information Security Management System
#### Control Implementation
#### Certification Goals

### Industry-Specific Standards
#### Standard 1: [Requirement]
#### Standard 2: [Requirement]

## Vulnerability Management

### Vulnerability Identification
#### Source Code Scanning
#### Dependency Scanning
#### Infrastructure Scanning
#### Penetration Testing

### Vulnerability Assessment
#### Severity Classification
#### CVSS Scoring
#### Risk Assessment
#### Impact Analysis

### Vulnerability Remediation
#### Remediation Timeline by Severity
#### Patch Management
#### Emergency Patching
#### Verification Testing

### Known Vulnerabilities Tracking
#### Vulnerability Database
#### Monitoring for New Vulnerabilities
#### Notification Process
#### Remediation Status

### Zero-Day Handling
#### Detection Process
#### Response Protocol
#### Communication Plan
#### Mitigation Steps

## Threat Modeling

### Identified Threats
#### Threat 1: [Threat Description]
#### Threat 2: [Threat Description]
#### Threat N: [Threat Description]

### Attack Surface
#### External Attack Surface
#### Internal Attack Surface
#### Supply Chain Attack Surface

### Threat Severity Assessment
#### High-Severity Threats
#### Medium-Severity Threats
#### Low-Severity Threats

### Mitigation Strategies
#### Threat 1 Mitigation
#### Threat 2 Mitigation
#### Threat N Mitigation

## Secure Coding Standards

### Code Review Requirements
#### Mandatory Code Review
#### Security Code Review
#### Review Checklist
#### Approval Authority

### Input Validation
#### Input Sanitization
#### Whitelisting/Blacklisting
#### SQL Injection Prevention
#### XSS Prevention
#### Command Injection Prevention

### Output Encoding
#### HTML Encoding
#### URL Encoding
#### JavaScript Encoding
#### CSS Encoding

### Error Handling
#### Error Message Security
#### Stack Trace Exposure Prevention
#### Logging Sensitive Data Prevention
#### User-Friendly Error Messages

### Dependency Management
#### Approved Dependencies
#### Dependency Scanning
#### Vulnerable Dependency Removal
#### Version Pinning

### OWASP Top 10 Mitigation
#### A01 - Broken Access Control
#### A02 - Cryptographic Failures
#### A03 - Injection
#### A04 - Insecure Design
#### A05 - Security Misconfiguration
#### A06 - Vulnerable Components
#### A07 - Authentication Failures
#### A08 - Data Integrity Failures
#### A09 - Logging & Monitoring Failures
#### A10 - SSRF

## API Security

### API Authentication
#### API Key Security
#### API Key Rotation
#### API Key Scope Limitation
#### API Key Revocation

### API Rate Limiting
#### Rate Limit Targets
#### DDoS Protection
#### Brute Force Prevention
#### Resource Exhaustion Prevention

### API Input Validation
#### Parameter Validation
#### Payload Size Limits
#### Content-Type Validation
#### Schema Validation

### API Output
#### Response Data Minimization
#### Sensitive Data Removal
#### Version Disclosure Prevention

### CORS (Cross-Origin Resource Sharing)
#### Allowed Origins
#### Allowed Methods
#### Allowed Headers
#### Credentials Handling

### API Documentation
#### Security Details in Docs
#### Sensitive Information Exclusion
#### Example Data Sanitization

## Webhook Security

### Webhook Authentication
#### Signature Verification
#### HMAC Implementation
#### Signature Algorithm
#### Verification Requirement

### Webhook Encryption
#### HTTPS Requirement
#### Certificate Validation
#### TLS Version

### Webhook Validation
#### Payload Validation
#### Content-Type Verification
#### Size Limits

### Webhook Retry Safety
#### Idempotency Keys
#### Duplicate Detection
#### Ordering Guarantee

## Infrastructure Security

### Network Security
#### Firewall Rules
#### Network Segmentation
#### VPN Requirements
#### DDoS Protection

### Server Security
#### OS Hardening
#### Patch Management
#### Unnecessary Services Disabled
#### File Integrity Monitoring

### Container Security
#### Container Scanning
#### Container Registry Security
#### Image Verification
#### Runtime Security

### Kubernetes Security
#### RBAC Configuration
#### Network Policies
#### Pod Security Policies
#### Admission Controllers

### Secrets Management
#### Secrets Storage Location
#### Secrets Rotation
#### Secrets Access Logging
#### Secrets Cleanup

### Logging & Monitoring
#### Security Event Logging
#### Log Retention
#### Log Encryption
#### Log Analysis

### Backup Security
#### Backup Encryption
#### Backup Access Control
#### Backup Testing
#### Disaster Recovery

## Third-Party Security

### Third-Party Risk Assessment
#### Vendor Security Assessment
#### SLA Requirements
#### Data Protection Agreements
#### Compliance Certification

### Third-Party Integrations
#### API Security Requirements
#### Data Sharing Restrictions
#### Authentication Security
#### Breach Notification Terms

### Vendor Dependency Management
#### Dependency Mapping
#### Risk Mitigation
#### Alternative Vendors
#### Contingency Plans

## Supply Chain Security

### Dependency Security
#### Dependency Scanning
#### Vulnerability Monitoring
#### License Compliance
#### Build Artifact Signing

### Source Code Security
#### Repository Access Control
#### Commit Signing
#### Code Review Requirements
#### Branch Protection

### Artifact Security
#### Artifact Signing
#### Artifact Verification
#### Artifact Distribution
#### Artifact Integrity

## Security Testing & Validation

### Penetration Testing
#### Testing Frequency
#### Testing Scope
#### Testing Methodology
#### Remediation Timeline

### Security Code Review
#### Review Frequency
#### Review Scope
#### Checklist Items
#### Approval Process

### Dynamic Application Security Testing (DAST)
#### DAST Tools
#### Testing Frequency
#### Test Scenarios
#### Finding Severity

### Static Application Security Testing (SAST)
#### SAST Tools
#### Scan Frequency
#### Baseline vs Delta Analysis
#### Finding Remediation

### Software Composition Analysis (SCA)
#### Dependency Scanning
#### License Compliance
#### Vulnerability Monitoring
#### Update Management

### Security Testing in CI/CD
#### Pre-Commit Checks
#### Build-Time Scanning
#### Pre-Release Testing
#### Production Verification

## Incident Response & Recovery

### Incident Response Plan
#### Response Team
#### Communication Protocol
#### Escalation Path
#### Incident Categories

### Detection & Response
#### Security Event Monitoring
#### Alert Thresholds
#### Incident Confirmation
#### Initial Response Steps

### Breach Notification
#### Notification Timeline
#### Notification Recipients
#### Notification Content
#### Regulatory Reporting

### Recovery Process
#### Service Restoration
#### Data Restoration
#### Forensics Analysis
#### Root Cause Analysis

### Post-Incident Activities
#### Incident Documentation
#### Lessons Learned
#### Control Enhancement
#### Communication Update

## Security Monitoring & Observability

### Security Event Logging
#### Events to Log
#### Log Format
#### Log Retention
#### Log Integrity

### Alerts & Detection
#### Alert Types
#### Alert Thresholds
#### Alert Routing
#### False Positive Management

### Monitoring Dashboard
#### Real-Time Monitoring
#### Historical Trends
#### Anomaly Detection
#### Threat Intelligence

## Physical Security

### Data Center Security
#### Access Controls
#### Surveillance
#### Environmental Controls
#### Visitor Management

### Workstation Security
#### Encryption Requirements
#### Screen Lock Policies
#### Device Management
#### Remote Work Security

### Paper Document Security
#### Classification
#### Handling
#### Storage
#### Destruction

## Employee Security & Awareness

### Security Training
#### Mandatory Training
#### Training Frequency
#### Phishing Simulations
#### Incident Response Drills

### Access Control
#### Principle of Least Privilege
#### Access Request Process
#### Access Approval
#### Access Removal

### Offboarding Process
#### Account Deactivation
#### Access Removal
#### Data Return
#### Exit Interview

### Insider Threat Program
#### Threat Indicators
#### Monitoring Approach
#### Incident Response
#### Privacy Considerations

## Security Policy & Standards

### Password Policy
#### Complexity Requirements
#### Length Requirements
#### Expiration Policy
#### Reuse Policy

### Device Policy
#### Device Types Allowed
#### Management Requirements
#### Encryption Requirements
#### Loss/Theft Reporting

### Acceptable Use Policy
#### Appropriate Use
#### Prohibited Activities
#### Monitoring Approach
#### Enforcement

### Bring Your Own Device (BYOD)
#### BYOD Approval
#### Security Requirements
#### Data Protection
#### Remote Management

## Security Compliance Auditing

### Internal Audits
#### Audit Frequency
#### Audit Scope
#### Audit Checklist
#### Remediation Tracking

### External Audits
#### Audit Type (SOC 2, ISO 27001, etc.)
#### Audit Frequency
#### Compliance Certification
#### Remediation Process

### Security Metrics & Reporting
#### Metrics Tracked
#### Reporting Frequency
#### Executive Reporting
#### Trend Analysis

## Security Governance

### Security Committee
#### Committee Members
#### Meeting Frequency
#### Decision Authority
#### Escalation Path

### Policy Review & Updates
#### Review Frequency
#### Update Process
#### Stakeholder Input
#### Communication Plan

### Risk Management
#### Risk Identification
#### Risk Assessment
#### Risk Mitigation
#### Risk Monitoring

## Security Roadmap

### Current Security Posture
#### Strengths
#### Gaps
#### Risk Areas

### Short-Term Improvements (Next Quarter)
#### Planned Improvements
#### Timeline
#### Resources Required

### Medium-Term Improvements (Next Year)
#### Strategic Initiatives
#### Technology Changes
#### Process Improvements

### Long-Term Vision
#### Security Architecture Evolution
#### Capability Maturity
#### Compliance Goals

## Incident Categories & Response

### Category 1: Data Breach
#### Definition
#### Response Timeline
#### Notification Requirements
#### Documentation

### Category 2: Unauthorized Access
#### Definition
#### Response Timeline
#### Investigation Steps
#### Remediation

### Category 3: Malware/Ransomware
#### Definition
#### Detection Methods
#### Containment Steps
#### Recovery Process

### Category 4: DDoS Attack
#### Definition
#### Mitigation Strategy
#### Communication Plan
#### Recovery Timeline

### Category 5: Service Disruption
#### Definition
#### Impact Assessment
#### Response Steps
#### Communication

## Security Tools & Technologies

### Approved Security Tools
#### SIEM Tool
#### Vulnerability Scanner
#### DAST Tool
#### SAST Tool
#### WAF Provider

### Integration with CI/CD
#### Pre-Commit Hooks
#### Build-Time Scanning
#### Deployment Checks
#### Production Monitoring

## FAQ
### Q: What's considered sensitive data?
### Q: Who needs multi-factor authentication?
### Q: What should I do if I suspect a breach?
### Q: How often are security patches applied?
### Q: What's the password policy?