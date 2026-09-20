# ClaimFlow — Cloud-Based Insurance Claims Management System

Starter code for the MCD1054 Cloud Computing Management final assessment.
Follow **Appendix A** of the technical report; it explains every step.

    app/         Flask web portal + REST API (containerised)
    function/    Azure Function, blob-triggered claim triage
    vm/          Nightly batch report that runs on the virtual machine
    sql/         Database schema and synthetic seed data
    tests/       Unit tests for the risk rules
    .github/     CI/CD pipeline (GitHub Actions)

All data in this repository is synthetic. No real customer information is used.
