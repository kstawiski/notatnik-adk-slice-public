# Business One-Pager

## One-Line Case

Notatnik Medyczny targets a narrow but expensive workflow: oncology documentation that must remain source-grounded, evidence-aware, and physician-approved under GDPR.

Product status: Notatnik Medyczny has a public product site at https://notatnikmedyczny.pl. This challenge submission isolates a judgeable, synthetic ADK reliability layer from the private production product.

Validation status: the challenge artifact is a public reliability slice, not a clinical outcomes claim. The next external milestone is a physician-design-partner pilot that measures minutes saved per documentation-heavy oncology encounter, contradiction/gap capture rate, generated-output scrub findings, and post-review edit burden.

## Beachhead

Initial wedge:

- Radiation oncology and multidisciplinary oncology documentation in Poland.
- Expansion path: oncology departments and outpatient oncology centers across EMEA.
- Buyer/user: physicians and clinic operators who pay for time saved, safer documentation, and auditability.

## Demand Drivers

- Clinical documentation burden is a recognized driver of physician burnout and inefficiency. A large EHR study reported average note time of 9.1 minutes per visit, with longer notes among medical specialists and additional burden for the longest-note physicians. Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC10154172/
- European oncology workforce pressure is a live policy issue. The European Cancer Organisation has warned that cancer workforce shortages are affecting frontline oncology care. Source: https://www.europeancancer.org/resources/publications/under-pressure-safeguarding-the-health-of-europes-oncology-workforce.html
- ESMO frames the oncology workforce as central to Europe's cancer-care capacity and notes that oncologists collectively see millions of new cancer patients annually. Source: https://www.esmo.org/content/download/793251/18763476/1/ESMO-Manifesto-for-a-Healthier-Europe.pdf

## ROI Scenario

This is a buyer ROI model, not a production outcome claim from the challenge repo.

Assumptions for one oncology clinician:

- 25 documentation-heavy encounters per week.
- 44 working weeks per year.
- 5-10 minutes saved per encounter after physician review.

Annual time released:

| Minutes saved / encounter | Hours released / year |
|---:|---:|
| 5 | 91.7 |
| 10 | 183.3 |

If fully loaded clinical time is valued at EUR 75-125/hour, the value range is approximately:

| Minutes saved / encounter | EUR 75/hour | EUR 125/hour |
|---:|---:|---:|
| 5 | EUR 6.9k/year | EUR 11.5k/year |
| 10 | EUR 13.8k/year | EUR 22.9k/year |

The pricing implication is straightforward: even a modest per-clinician subscription can be justified if the product reliably releases 5 minutes per documentation-heavy encounter while preserving clinical oversight.

## Defensibility

- Domain specificity: oncology staging, biomarkers, margins, nodal status, evidence, and trial prescreening are not generic note-writing.
- Regulatory posture: GDPR-aware design, synthetic public demo, physician-in-the-loop framing.
- Reliability discipline: measured before/after reliability profile, held-out test split, explicit negative finding, deterministic mitigation.
- IP protection: proprietary Notatnik clinical prompts and recognizers stay private; the submitted project exposes only the public engineering slice and MCP data-tool boundary.

## Go-To-Market

1. Founder-led design partner: the founder's oncology/radiotherapy practice workflow.
2. First external design-partner pilot: run in physician-review mode, with synthetic/public demo separated from any private clinical data and with a GDPR/DPIA review before processing real patient material.
3. Polish oncology practices and clinics with documentation-heavy workflows.
4. EMEA oncology centers that need documentation efficiency without autonomous clinical decision-making.

## Commercial Summary

This is a credible B2B healthcare wedge: a practicing oncologist has built the product, the demo focuses on a measured reliability problem, and the architecture protects both patients and clinical IP.
