# Access Matrix

Complete this matrix before implementing semantic retrieval. Use `Allow` or `Deny` in every relevant cell and explain any decision that is not obvious. The column names match the exact roles implemented in the starter.

| Source or record class | Customer Success | Engineering | People Operations | Finance | Owner and reason |
| --- | --- | --- | --- | --- | --- |
| General company handbook | Allow | Allow | Allow | Allow | Company-wide operating guidance |
| Customer communications | Decide | Decide | Decide | Decide | |
| Local GitHub work items | Decide | Decide | Decide | Decide | |
| Live GitHub work items | Decide | Decide | Decide | Decide | |
| Financial records | Decide | Decide | Decide | Decide | |
| Restricted HR records | Deny | Deny | Allow | Deny | People Operations only |

## Source Governance

| Source | Stable ID strategy | Citation target | Update or deletion policy | Fallback |
| --- | --- | --- | --- | --- |
| Slack export | | | | |
| Email export | | | | |
| Documents | | | | |
| Local GitHub export | | | | |
| Live GitHub repository | | | | |
| SQLite records | | | | |

## Enforcement Notes

- **Identity source in the prototype:**
- **Where filtering happens:**
- **Default when metadata is missing:**
- **How citations are rechecked:**
- **How live API access differs from employee authorization:**
- **Where GitHub credentials are stored:**
- **How identity is rechecked before an approved action:**
- **What the prototype does not secure yet:**
- **Evidence that unauthorized content is excluded before retrieval:**
