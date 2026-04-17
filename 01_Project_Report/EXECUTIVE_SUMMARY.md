# Executive Summary

This project delivers a complete local email intelligence prototype built around two main machine learning tasks:

- spam/phishing detection
- importance estimation for legitimate emails

The technical contribution goes beyond a standard notebook by including:

- exported reusable pipelines
- a Gmail-style local application
- event extraction and calendar integration
- smart folders
- a blind synthetic stress test

The original hold-out split produced perfect spam metrics, but a stricter blind synthetic evaluation showed that the model is mainly limited by false positives on realistic legitimate emails. This makes the final report more rigorous and more honest.

The final application demonstrates how the models can be used inside a realistic interface, including generated demo emails and smart mailbox organization.
