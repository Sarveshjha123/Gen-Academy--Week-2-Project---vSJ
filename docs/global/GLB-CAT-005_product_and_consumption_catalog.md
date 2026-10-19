---
doc_id: GLB-CAT-005
title: Product and Consumption Catalog
doc_type: catalog
ou: GLOBAL
effective_from: 2026-02-01
effective_to: 2027-01-31
products: A; B; C; D; E; F; G; H; I; J
company: Cloudpaw Inc. (fictional)
fiscal_year: FY27
owner: Global Renewals & Deal Desk
---

> Fictional data for a course project. Cloudpaw, its products, prices, policies, programs, customers and people are invented.

# Product and Consumption Catalog (FY27, USD list prices)

Cloudpaw sells 10 products. Seat products are billed per licensed user; consumption products are billed on a committed annual quantity.

| Code | Product | Pricing model | List price | Utilization measure | Per-user consumption signal |
|---|---|---|---|---|---|
| A | Sales CRM | Seat | $1,200 per seat / year | Active users ÷ seats | Opportunities updated per active user per month |
| B | Service Desk | Seat | $1,100 per seat / year | Active agents ÷ seats | Cases closed per agent per month |
| C | Analytics & BI | Seat | $900 per seat / year | Active users ÷ seats | Dashboard views per user per month |
| D | Team Chat | Seat | $150 per seat / year | Active users ÷ seats | Messages per active user per month |
| E | Customer Data Platform | Consumption | $0.06 per credit | Credits used ÷ monthly commitment | Credits per active user per month |
| F | AI Agents | Consumption | $0.10 per credit | Credits used ÷ monthly commitment | Credits per active user per month |
| G | Marketing Automation | Consumption | $3,000 per million messages | Messages sent ÷ monthly commitment | Million messages per marketing user per month |
| H | Commerce | Consumption | 1.5% of committed GMV | GMV processed ÷ monthly commitment | GMV per active user per month |
| I | Customer Portal | Consumption | $0.40 per member login | Logins ÷ monthly commitment | Logins per portal admin per month |
| J | Integration Platform | Consumption | $200 per million API calls | Calls ÷ monthly commitment | Million calls per integration owner per month |

## How utilization is measured
- **Seat products:** utilization = active users in the month ÷ licensed seats. Cannot exceed 100%.
- **Consumption products:** utilization = quantity consumed in the month ÷ (committed annual quantity ÷ 12). Can exceed 100% (overage).

## Product rules
- Product F (AI Agents) requires Product A or Product B on the same account.
- Product H (Commerce) has a minimum commitment of $1,000,000 GMV per year.
- Product I (Customer Portal) is commonly bought by Public Sector, Healthcare and Education customers.
