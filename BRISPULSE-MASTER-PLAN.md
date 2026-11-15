# BrisPulse — Product & Engineering Master Plan

**Version:** 1.0
**Date:** November 2026
**Product:** BrisPulse
**Product Category:** Mobility Intelligence Platform
**Initial Release:** Functional MVP
**Primary Market:** Brisbane, Queensland, Australia

---

## 1. Executive Summary

### 1.1 Product Vision

BrisPulse is a Brisbane Mobility Intelligence Platform that transforms public transport data into meaningful, accessible, and actionable mobility insights.

The goal is to move beyond a conventional public transport tracking dashboard.

Rather than simply displaying where vehicles are located, BrisPulse aims to help users understand:

* Current public transport conditions.
* Service disruptions and delays.
* Route-level service performance.
* Distribution of reported delays.
* Historical mobility patterns.
* Changes in public transport service reliability.

The platform will initially focus on Brisbane and the South East Queensland public transport network.

### 1.2 Product Direction

The selected product direction is:

**B. Mobility Intelligence Platform**

The initial release will be a functional MVP.

The product will be developed progressively, beginning with reliable real-time transport monitoring and expanding into descriptive mobility analytics.

Predictive analytics, AI-powered recommendations, and advanced smart-city decision support are future possibilities, not MVP requirements.

### 1.3 Core Product Philosophy

BrisPulse should prioritise:

1. Real data over mock data.
2. Reliable information over visual complexity.
3. Meaningful analytics over unnecessary AI features.
4. Maintainable engineering over premature optimisation.
5. A functional deployed product over an unfinished ambitious prototype.

The objective is to deliver a genuinely usable application that demonstrates real-world full-stack engineering capabilities.

---

## 2. Product Objectives

### 2.1 Primary Objectives

The MVP should demonstrate that BrisPulse can:

1. Retrieve genuine Brisbane public transport data.
2. Process and normalise transport information.
3. Present useful information through a web application.
4. Identify and communicate service disruptions.
5. Calculate meaningful descriptive mobility metrics.
6. Preserve historical data where necessary.
7. Operate reliably as a deployed application.

### 2.2 Target Users

Initial target users include:

* Brisbane public transport passengers.
* People interested in public transport conditions.
* Users interested in mobility and urban transport patterns.
* Developers and researchers exploring transport data.

The initial product should prioritise information clarity and accessibility rather than building complicated user management or personalisation features.

### 2.3 Value Proposition

BrisPulse should answer three questions:

**Monitoring** — What is happening across Brisbane public transport right now?

**Analytics** — Which routes and services are experiencing delays or disruptions?

**Intelligence** — How are public transport service conditions changing over time?

---

## 3. Product Scope

### 3.1 MVP Feature Categories

#### A. Mobility Monitoring

Essential capabilities:

* Overview of available transport services.
* Vehicle positions where available.
* Interactive map.
* Route and service information.
* Active service alerts.
* Trip delay information where supported.
* Last updated timestamps.
* Clear data freshness indicators.

#### B. Mobility Analytics

Initial capabilities:

* Number of reported active vehicles.
* Number of active service alerts.
* Route-level delay distribution.
* Reported delay summaries.
* Service disruption statistics.
* Basic historical trends when sufficient data has been collected.

#### C. Data Reliability

The platform must:

* Distinguish live data from scheduled data.
* Identify stale or missing information.
* Handle upstream API failures.
* Avoid presenting unavailable information as zero.
* Display appropriate error and empty states.
* Record data retrieval timestamps.

### 3.2 Future Features

The following are explicitly outside the initial MVP scope:

* AI-based traffic predictions.
* Machine learning forecasting.
* Automated route recommendations.
* Personalised commuter recommendations.
* Citywide road congestion analysis.
* Complex multi-modal journey optimisation.
* Advanced smart-city decision support.
* User accounts and personalisation unless required by an existing working feature.

These features may be considered after the MVP is deployed and its data foundation is proven.

### 3.3 Scope Control

Do not expand the MVP simply because a feature is technically interesting.

Every proposed feature should be evaluated against:

* User value.
* Data availability.
* Implementation complexity.
* Operational cost.
* Reliability.
* Relevance to the product vision.

---

## 4. Data Sources and Integration Strategy

### 4.1 Primary Data Source

TransLink is the primary candidate for Brisbane and South East Queensland public transport data.

Official resources:

* https://translink.com.au/about-translink/open-data
* https://www.data.qld.gov.au/dataset/translink-real-time-data

The exact developer access method, feed availability, authentication requirements, licensing, and technical limitations must be independently verified during Technical Discovery.

Do not assume that every data feed is publicly accessible or provides complete network coverage.

### 4.2 GTFS Static

Investigate the availability of GTFS static data.

Potential information:

* Routes.
* Stops.
* Trips.
* Service calendars.
* Scheduled stop times.
* Route and stop relationships.

Purpose:

Provide the static transport network structure required to interpret real-time transport information.

### 4.3 GTFS-Realtime

Investigate the availability and reliability of:

**Vehicle Positions**

Potential information:

* Vehicle location.
* Vehicle identifier.
* Associated trip.
* Timestamp.
* Position-related metadata.

**Trip Updates**

Potential information:

* Predicted arrival and departure times.
* Stop-level delays.
* Trip update information.

**Service Alerts**

Potential information:

* Service disruptions.
* Affected routes.
* Affected stops.
* Alert descriptions.
* Active periods.

### 4.4 Data Verification Requirements

Before implementing integrations, verify:

* Official access method.
* Authentication requirements.
* Endpoint availability.
* Feed format.
* Protobuf decoding requirements.
* Update frequency.
* Data freshness.
* Network coverage.
* Missing or incomplete records.
* Usage restrictions.
* Attribution requirements.

Clearly distinguish between documented capabilities and observed live behaviour.

### 4.5 Data Quality Principles

BrisPulse must never:

* Invent vehicle positions.
* Fabricate delay values.
* Treat missing data as zero.
* Present stale information as live.
* Claim full network coverage without evidence.
* Infer road congestion from public transport vehicle positions alone.

Every important metric must have a documented definition and known limitations.

---

## 5. Mobility Analytics Strategy

The platform should begin with descriptive analytics.

Predictive analytics will only be considered after the data collection foundation is reliable.

### 5.1 Candidate Metrics

**Active Vehicle Count**

Count valid and sufficiently fresh vehicle position records.

The definition of active must account for the feed timestamp and an appropriate freshness threshold.

**Active Service Alerts**

Count currently applicable alerts according to their active periods and affected services.

**Route-Level Delay Distribution**

Summarise reported delays associated with trips on each route.

Possible outputs:

* Number of reported delayed trips.
* Delay distribution.
* Median reported delay.
* Maximum reported delay.

Only calculate these values when the required data is available.

**Service Reliability**

Explore an on-time performance proxy.

Important:

A valid on-time performance calculation requires an appropriate scheduled-versus-actual or predicted-versus-scheduled comparison.

Do not claim that a single snapshot of GTFS-Realtime data represents definitive service reliability.

**Historical Mobility Trends**

Potential analysis:

* Delay trends over time.
* Service alert frequency.
* Route-level disruption patterns.
* Changes in reported service conditions.

Historical analytics requires BrisPulse to collect and retain sufficient historical observations.

### 5.2 Metric Documentation

Every published metric must document:

* Metric name.
* Definition.
* Data source.
* Calculation method.
* Update frequency.
* Coverage limitations.
* Known accuracy limitations.

---

## 6. Technical Architecture Principles

### 6.1 General Approach

Inspect the existing BrisPulse implementation before choosing or replacing technologies.

Retain useful existing components wherever practical.

Do not redesign the entire system simply to adopt a preferred technology.

### 6.2 Proposed Logical Architecture

The architecture should contain the following logical layers.

**Layer 1: External Data Sources**

* TransLink GTFS Static.
* TransLink GTFS-Realtime.
* Other verified supporting data sources if justified.

**Layer 2: Data Ingestion**

Responsibilities:

* Retrieve source data.
* Decode incoming formats.
* Validate records.
* Normalise transport entities.
* Handle incomplete or invalid responses.
* Track retrieval timestamps.

**Layer 3: Backend and Data Processing**

Responsibilities:

* Expose application APIs.
* Process transport information.
* Associate real-time records with static schedules.
* Calculate supported metrics.
* Cache frequently requested information.
* Store historical observations where necessary.

**Layer 4: Data Storage**

Select storage based on actual requirements.

Potential responsibilities:

* Static transport reference data.
* Normalised transport information.
* Historical snapshots.
* Service alert history.
* Data retrieval metadata.

Do not introduce a database or storage system without a clear requirement.

**Layer 5: Frontend**

Responsibilities:

* Mobility overview.
* Interactive transport map.
* Route and service details.
* Service alert presentation.
* Mobility analytics.
* Data freshness indicators.
* Responsive user experience.

### 6.3 Architecture Evaluation Criteria

Evaluate:

* Maintainability.
* Implementation complexity.
* Reliability.
* Deployment compatibility.
* Operational cost.
* Data processing requirements.
* Scalability appropriate to the MVP.

Avoid premature microservices and unnecessary infrastructure.

---

## 7. Model Responsibilities and AI Workflow

The project will use Sonnet 5.5 and Fable 5.2 with distinct responsibilities.

The goal is to use the advanced model for high-value engineering decisions and difficult implementation work.

### 7.1 Sonnet 5.5 — Discovery and Supporting Engineering

Primary responsibilities:

* Repository exploration.
* Existing implementation audit.
* Documentation review.
* Data source research.
* API feasibility investigation.
* Initial technical architecture proposals.
* Requirements documentation.
* General UI implementation.
* Component development.
* Test preparation.
* Documentation updates.

Sonnet must provide evidence from the repository and clearly distinguish verified facts from assumptions.

Sonnet should not modify application source code during the initial discovery phase.

### 7.2 Fable 5.2 — Principal Engineering

Primary responsibilities:

* Independent architecture review.
* Technical decision validation.
* Complex backend implementation.
* Data ingestion pipeline.
* GTFS and GTFS-Realtime integration.
* Data processing and normalisation.
* Database and API design.
* Frontend/backend integration.
* Difficult debugging.
* End-to-end testing review.
* Production readiness assessment.

Fable is expected to challenge unsupported technical assumptions rather than blindly following the initial discovery documents.

### 7.3 Collaborative Workflow

The preferred workflow is:

1. Sonnet investigates.
2. Sonnet documents findings.
3. Fable independently validates findings.
4. Fable proposes the final architecture.
5. Human approval is obtained for major decisions.
6. Fable implements complex engineering components.
7. Sonnet supports general implementation and documentation.
8. Fable performs final technical review.

Model allocation is flexible.

Do not force every task into a particular model if another model is more appropriate.

### 7.4 Usage Optimisation

The free reset voucher for Fable 5.2 should be reserved for high-value engineering work.

Recommended priorities:

* Architecture validation.
* Complex data processing.
* Backend implementation.
* Integration debugging.
* Production readiness.

Routine documentation and straightforward UI modifications should generally use Sonnet.

The objective is to maximise engineering output rather than simply maximise model usage.

---

## 8. Development Roadmap

### M0 — Technical Discovery

**Primary model:** Sonnet 5.5

**Objective:** Understand the current implementation and establish a verified technical baseline.

Tasks:

* Inspect the entire BrisPulse implementation.
* Identify existing functional features.
* Identify mock data and placeholders.
* Review existing architecture.
* Investigate TransLink data sources.
* Evaluate metric feasibility.
* Identify technical risks.
* Document unresolved questions.

Deliverables:

* `BRISPULSE-REPOSITORY-AUDIT.md`
* `BRISPULSE-DATA-SOURCE-RESEARCH.md`
* `BRISPULSE-METRICS-FEASIBILITY.md`
* `BRISPULSE-MVP-REQUIREMENTS.md`
* `BRISPULSE-TECHNICAL-HANDOFF.md`

Acceptance criteria:

* Existing functionality is accurately documented.
* Data source feasibility is investigated.
* Proposed MVP scope is realistic.
* No application source code has been modified.

### M1 — Architecture Validation

**Primary model:** Fable 5.2

**Objective:** Establish an implementation-ready architecture.

Tasks:

* Review Sonnet's technical findings.
* Verify important assumptions.
* Select appropriate technologies.
* Define data ingestion strategy.
* Define API contracts.
* Define data models.
* Define update and caching strategies.
* Define error handling.
* Establish acceptance criteria.

Deliverable:

* `BRISPULSE-ARCHITECTURE.md`

Acceptance criteria:

* Architecture decisions are documented.
* Major technical risks are identified.
* Implementation milestones are clear.
* Human approval is obtained before major implementation.

### M2 — Data Pipeline and Backend

**Primary model:** Fable 5.2

**Objective:** Establish a reliable data foundation.

Tasks:

* Integrate verified GTFS static data.
* Integrate available GTFS-Realtime feeds.
* Decode Protobuf where required.
* Validate and normalise data.
* Associate real-time information with static transport data.
* Implement backend API endpoints.
* Implement caching where appropriate.
* Handle upstream failures.
* Add appropriate logging.

Acceptance criteria:

* Genuine transport data can be retrieved.
* Data is processed correctly.
* Invalid and stale data is handled.
* Backend APIs return validated application data.
* Automated tests cover important processing logic.

### M3 — Mobility Monitoring Dashboard

**Primary models:** Sonnet 5.5 + Fable 5.2

**Objective:** Deliver the first usable frontend experience.

Features:

* Mobility overview.
* Interactive map.
* Vehicle positions where available.
* Route and service status.
* Service alerts.
* Reported delay information.
* Data freshness indicators.

Sonnet may implement general UI components.

Fable should handle complex integration and data-related issues.

Acceptance criteria:

* Frontend consumes the actual backend APIs.
* No critical feature depends on fabricated mock data.
* Loading, empty, and error states work correctly.
* Responsive behaviour is verified.
* Data freshness is communicated clearly.

### M4 — Mobility Analytics

**Primary model:** Fable 5.2

**Objective:** Transform transport monitoring into descriptive mobility intelligence.

Features:

* Active vehicle statistics.
* Service alert statistics.
* Route-level delay distribution.
* Reported delay summaries.
* Historical mobility trends when sufficient data is available.

Tasks:

* Define metric calculation methods.
* Implement aggregation logic.
* Store historical observations where necessary.
* Validate metric accuracy.
* Document limitations.

Acceptance criteria:

* Each metric has a documented definition.
* Metrics are calculated from genuine data.
* Historical metrics are based on collected observations.
* Incomplete data is not presented as definitive.

### M5 — Production Readiness and Deployment

**Models:** Sonnet 5.5 + Fable 5.2

**Objective:** Deliver a reliable publicly accessible application.

Tasks:

* Automated testing.
* Type checking.
* Linting.
* Production builds.
* Security review.
* Performance optimisation.
* Accessibility review.
* Responsive testing.
* Environment configuration.
* Deployment.
* Monitoring and operational documentation.

Acceptance criteria:

* Production build succeeds.
* Critical tests pass.
* Deployment is verified.
* Required environment variables are documented.
* External data failures are handled gracefully.
* Known limitations are documented.

---

## 9. MVP Acceptance Criteria

The MVP should not be considered complete simply because the frontend looks finished.

The following criteria must be satisfied.

**Data**

* Real transport data is integrated.
* Data source and timestamps are traceable.
* Data validation is implemented.
* Missing and stale data are handled correctly.

**Backend**

* Application APIs function correctly.
* Important processing logic is tested.
* API errors are handled.
* Secrets are not exposed.

**Frontend**

* Core monitoring features work.
* Map and service information are usable.
* Analytics are based on genuine data.
* Mobile and desktop layouts work.
* Loading and error states are present.

**Reliability**

* Upstream feed failures do not crash the entire application.
* Stale data is clearly identified.
* The application does not fabricate transport information.

**Deployment**

* Public deployment is accessible.
* Production build is verified.
* Configuration is documented.
* Known operational limitations are documented.

---

## 10. Engineering Standards

All implementation work should follow these principles.

**Code Quality**

* Maintain readable and modular code.
* Use existing project conventions.
* Avoid unnecessary abstractions.
* Avoid duplicate implementations.
* Use appropriate type safety.
* Keep dependencies justified.

**Security**

* Never commit API keys or credentials.
* Use environment variables appropriately.
* Validate external data.
* Avoid exposing internal errors or sensitive configuration.

**Testing**

Prioritise:

* Data parsing tests.
* Data validation tests.
* Metric calculation tests.
* API tests.
* Frontend integration tests.
* Critical end-to-end tests.

**Documentation**

Maintain documentation covering:

* Architecture.
* Data sources.
* API contracts.
* Metric definitions.
* Environment configuration.
* Deployment instructions.
* Known limitations.

**Git Workflow**

* Preserve the existing working baseline.
* Create a dedicated feature branch for major implementation.
* Commit changes in logical milestones.
* Avoid unrelated changes.
* Review diffs before merging.
* Never overwrite existing user work without permission.

---

## 11. Product Design Principles

BrisPulse should look like a professional mobility intelligence product rather than a generic student dashboard.

Design priorities:

1. Clear information hierarchy.
2. Data visualisation that communicates meaningful insights.
3. Consistent design system.
4. Useful map interactions.
5. Responsive layouts.
6. Accessible colour contrast.
7. Clear status indicators.
8. Minimal unnecessary animation.

The interface should prioritise usability and data clarity.

Visual complexity must not take priority over information accuracy.

---

## 12. Risk Management

Potential risks include:

**Data Availability** — Some feeds may require authentication or have incomplete coverage.
*Mitigation:* Verify source availability before committing to implementation.

**Data Quality** — Real-time records may be missing, delayed, or inconsistent.
*Mitigation:* Implement validation, freshness checks, and clear limitations.

**Historical Data** — Real-time feeds may not provide historical records.
*Mitigation:* Collect and store appropriate observations when justified.

**Scope Creep** — Mobility intelligence can expand into an unnecessarily large platform.
*Mitigation:* Maintain strict MVP boundaries.

**Deployment Complexity** — Data ingestion may require scheduled or continuously running processes that are not suitable for a basic serverless deployment.
*Mitigation:* Evaluate the existing hosting environment and choose an appropriate operational strategy.

**Development Model Reliability** — AI-generated code may introduce incorrect assumptions or unnecessary complexity.
*Mitigation:* Require independent review, testing, and evidence-based verification.

---

## 13. Portfolio Positioning

BrisPulse should become one of the flagship engineering projects in my professional portfolio.

It should demonstrate:

* Full-stack application development.
* External API integration.
* Data engineering.
* Backend architecture.
* Database design.
* Data analytics.
* Interactive frontend development.
* Testing and deployment.
* Technical decision-making.

The project case study should eventually explain:

1. The original problem.
2. The product vision.
3. The technical architecture.
4. The data engineering workflow.
5. Key engineering challenges.
6. Important technical decisions.
7. Verified implementation results.
8. Testing and deployment.
9. Future improvements.

Do not invent business impact or performance metrics.

Clearly distinguish completed functionality from future plans.

---

## 14. Definition of Success

BrisPulse will be considered a successful MVP when:

* It retrieves and processes genuine Brisbane public transport data.
* Users can interact with a functioning monitoring interface.
* The platform provides useful descriptive mobility analytics.
* The application handles missing and stale data appropriately.
* The system is deployed and accessible.
* Its technical architecture is documented.
* Its important functionality is tested.
* Its implementation can be confidently explained in a technical interview.

The ultimate goal is to demonstrate that BrisPulse is not merely a visual prototype, but a real, maintainable, data-driven full-stack application.

---

## 15. Instructions for AI Models

Any AI model contributing to BrisPulse must follow this Master Plan.

**Before starting a task:**

1. Read this document.
2. Inspect relevant repository files.
3. Understand existing implementations.
4. Identify dependencies.
5. Confirm the task's relationship to the MVP.

**During implementation:**

1. Work incrementally.
2. Preserve functioning features.
3. Verify assumptions.
4. Write maintainable code.
5. Test important changes.
6. Document decisions.

**After implementation:**

1. Report modified files.
2. Report actual test results.
3. Identify outstanding issues.
4. Update relevant documentation.
5. Distinguish completed work from planned work.

**Do not:**

* Invent data.
* Invent achievements.
* Claim unverified functionality.
* Introduce unnecessary technologies.
* Expand MVP scope without justification.
* Perform large rewrites without approval.

This Master Plan is the primary product and engineering reference for BrisPulse.

Technical findings may refine the implementation approach, but major changes to product direction and MVP scope require explicit approval.
