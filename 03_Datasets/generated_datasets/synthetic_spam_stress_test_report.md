# Synthetic Blind Stress Test for the Spam Pipeline

## Setup
- Seed: `20260413`
- Total emails: `720`
- Families: `12`
- Threshold used: `0.5`
- Blind inference: the pipeline predicted on rows with the `label` column removed before scoring.

## Overall results
- Accuracy: `0.7917`
- Precision: `0.7075`
- Recall: `0.9944`
- F1: `0.8268`
- Specificity: `0.5889`
- False positive rate on legitimate mail: `0.4111`
- False negative rate on spam/phishing mail: `0.0056`
- Confusion matrix counts: `TN=212, FP=148, FN=2, TP=358`

## Main readout
- The easiest legitimate family was `legit_internal_project`.
- The hardest legitimate family was `legit_newsletter_marketing`.
- The easiest spam/phishing family was `spam_prize_lottery`.
- The hardest spam/phishing family was `phishing_ceo_wire`.

## Metrics by family
```text
                     family label_type  n_rows  accuracy  precision  recall     f1  specificity  false_positive_rate  false_negative_rate  avg_spam_probability  tn  fp  fn  tp
      legit_calendar_invite legitimate      60    0.8667        0.0  0.0000 0.0000       0.8667               0.1333               0.0000                0.1566  52   8   0   0
     legit_internal_project legitimate      60    1.0000        0.0  0.0000 0.0000       1.0000               0.0000               0.0000                0.0000  60   0   0   0
       legit_invoice_notice legitimate      60    1.0000        0.0  0.0000 0.0000       1.0000               0.0000               0.0000                0.0567  60   0   0   0
 legit_newsletter_marketing legitimate      60    0.0000        0.0  0.0000 0.0000       0.0000               1.0000               0.0000                0.9997   0  60   0   0
      legit_security_notice legitimate      60    0.6667        0.0  0.0000 0.0000       0.6667               0.3333               0.0000                0.4019  40  20   0   0
legit_shipping_confirmation legitimate      60    0.0000        0.0  0.0000 0.0000       0.0000               1.0000               0.0000                0.9990   0  60   0   0
          phishing_ceo_wire  spam_like      60    0.9667        1.0  0.9667 0.9831       0.0000               0.0000               0.0333                0.7012   0   0   2  58
    phishing_document_share  spam_like      60    1.0000        1.0  1.0000 1.0000       0.0000               0.0000               0.0000                0.9379   0   0   0  60
    phishing_payroll_update  spam_like      60    1.0000        1.0  1.0000 1.0000       0.0000               0.0000               0.0000                0.9764   0   0   0  60
            spam_parcel_fee  spam_like      60    1.0000        1.0  1.0000 1.0000       0.0000               0.0000               0.0000                0.9950   0   0   0  60
         spam_prize_lottery  spam_like      60    1.0000        1.0  1.0000 1.0000       0.0000               0.0000               0.0000                1.0000   0   0   0  60
  spam_subscription_renewal  spam_like      60    1.0000        1.0  1.0000 1.0000       0.0000               0.0000               0.0000                1.0000   0   0   0  60
```

## Metrics by difficulty
```text
difficulty  n_rows  accuracy  precision  recall     f1  specificity  false_positive_rate  false_negative_rate  avg_spam_probability  tn  fp  fn  tp
      easy     120    1.0000     1.0000  1.0000 1.0000       1.0000               0.0000               0.0000                0.5000  60   0   0  60
      hard     360    0.6056     0.5597  0.9889 0.7149       0.2222               0.7778               0.0111                0.8360  40 140   2 178
    medium     240    0.9667     0.9375  1.0000 0.9677       0.9333               0.0667               0.0000                0.5521 112   8   0 120
```

## Metrics by broad type
```text
coarse_type  n_rows  accuracy  precision  recall     f1  specificity  false_positive_rate  false_negative_rate  avg_spam_probability  tn  fp  fn  tp
 legitimate     360    0.5889        0.0  0.0000 0.0000       0.5889               0.4111               0.0000                0.4357 212 148   0   0
   phishing     180    0.9889        1.0  0.9889 0.9944       0.0000               0.0000               0.0111                0.8718   0   0   2 178
       spam     180    1.0000        1.0  1.0000 1.0000       0.0000               0.0000               0.0000                0.9983   0   0   0 180
```

## Sample false positives
```text
                    family difficulty                            subject       from_domain  num_urls  contains_tracking_token  spam_probability
legit_newsletter_marketing       hard         Workflow automation launch notifications.net         2                     True          0.999962
legit_newsletter_marketing       hard         Workflow automation launch notifications.net         2                     True          0.999955
legit_newsletter_marketing       hard Dashboard performance improvements notifications.net         2                     True          0.999951
legit_newsletter_marketing       hard    Security controls now available       example.com         2                     True          0.999951
legit_newsletter_marketing       hard         Workflow automation launch notifications.net         2                     True          0.999947
legit_newsletter_marketing       hard    Security controls now available       example.com         2                     True          0.999943
legit_newsletter_marketing       hard         Workflow automation launch notifications.net         2                     True          0.999942
legit_newsletter_marketing       hard              New analytics widgets notifications.net         2                     True          0.999939
legit_newsletter_marketing       hard              New analytics widgets notifications.net         2                     True          0.999939
legit_newsletter_marketing       hard         Workflow automation launch notifications.net         2                     True          0.999935
legit_newsletter_marketing       hard              April product updates notifications.net         2                     True          0.999935
legit_newsletter_marketing       hard              New analytics widgets       example.com         2                     True          0.999935
legit_newsletter_marketing       hard    Security controls now available        adatum.net         2                     True          0.999930
legit_newsletter_marketing       hard Dashboard performance improvements notifications.net         2                     True          0.999929
legit_newsletter_marketing       hard              New analytics widgets notifications.net         2                     True          0.999923
```

## Sample false negatives
```text
           family difficulty                             subject   from_domain  num_urls  contains_tracking_token  spam_probability
phishing_ceo_wire       hard Need your help with a payment today mycompany.com         0                    False          0.431472
phishing_ceo_wire       hard Need your help with a payment today mycompany.com         0                    False          0.447279
```

## Interpretation
- If false positives cluster around legitimate emails with URLs, HTML and tracking tokens, the model is likely overfitted to the original dataset pattern where legitimate emails almost never contain links.
- If false negatives cluster around polished phishing or CEO-style fraud without links, the model is probably relying too much on easy metadata such as URL count and authentication failure.
- This report is more realistic than the original hold-out score because every example here was generated after training and scored in blind mode.
