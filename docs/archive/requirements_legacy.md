Here is your **complete Markdown file** — clean, structured, and ready to give to Claude or any developer.

---

```markdown
# 📘 Machine Shop Planning Software – Full Specification

---

# 1. Objective

Build a **simple, rule-based machine shop planning tool** for a high-mix valve manufacturing setup.

## Goals
- Achieve ₹2.5 Cr/week throughput  
- Predict machine load for next 7–10 days  
- Identify overload before it happens  
- Recommend subcontracting decisions  
- Support valve completion and OTD  

---

# 2. Input Data Structure

## 2.1 Valve Plan

| Field | Description |
|------|------------|
| Valve_ID | Unique valve identifier |
| Order_ID | Work order number |
| Customer | Customer name |
| Dispatch_Date | Planned dispatch date |
| Assembly_Date | Planned assembly date |
| Value | ₹ value |

---

## 2.2 Component Status

| Field | Description |
|------|------------|
| Valve_ID | Parent valve |
| Component | Component name |
| Qty | Quantity |
| Fabrication_Required | Yes/No |
| Fabrication_Complete | Yes/No |
| Expected_Ready_Date | Expected date from fabrication |
| Critical | Yes/No |

---

## 2.3 Routing Master

| Field | Description |
|------|------------|
| Component | Component name |
| Operation_No | Operation sequence |
| Operation_Name | Process step |
| Machine_Type | Required machine |
| Alt_Machine | Alternate machine (if any) |
| Std_Time_Hrs | Standard machining time |
| Subcontract | Yes/No |

---

## 2.4 Machine Master

| Field | Description |
|------|------------|
| Machine_ID | Unique ID |
| Machine_Type | HBM / VTL / Lathe etc. |
| Hours_per_Day | Available hours |
| Efficiency | Practical efficiency (%) |
| Buffer_Days | Allowed queue buffer |

---

## 2.5 Vendor Master

| Field | Description |
|------|------------|
| Vendor_ID | Unique ID |
| Process | Capability |
| Turnaround_Days | Total vendor cycle time |
| Capacity | Load capability |

---

# 3. Core Planning Rules

## 3.1 Planning Horizon
- Default: 7 days  
- Optional: 14 days  

---

## 3.2 Priority Activation
A component becomes eligible only when:
- Fabrication is complete (FCC available)

---

## 3.3 Priority Logic
1. Full-kit valves (all critical components ready)  
2. Near full-kit valves  
3. Other valves (only if spare capacity exists)  

---

## 3.4 Machine Load Calculation

```

Load (days) = Total Operation Hours / (Hours_per_Day × Efficiency)

```

---

## 3.5 Buffer Logic

| Machine | Buffer |
|--------|--------|
| HBM | 4 days |
| VTL | 3 days |
| Lathe | 2 days |
| Drill / Others | 2–3 days |

---

## 3.6 Overload Condition

```

If Load > Buffer → Machine is Overloaded

```

---

## 3.7 Subcontract Logic

If:
- Machine load exceeds buffer  
- Subcontract is allowed  
- Vendor turnaround is faster than internal delay  

Then:
- Recommend subcontracting  

---

## 3.8 Pre-emptive Decision Rule

- Subcontract decision must be made **before job arrives**  
- Component should go **directly to vendor on receipt**

---

## 3.9 Alternate Machine Rule

- If alternate machine is available  
- And has capacity  

Then:
- Prefer alternate machine over subcontracting  

---

# 4. System Processing Logic

## Step 1: Read Input Data
- Valve Plan  
- Component Status  
- Routing Master  
- Machine Master  
- Vendor Master  

---

## Step 2: Identify Incoming Components
- Select components expected in next 7–10 days  

---

## Step 3: Filter by Priority
- Include only components with fabrication completion  
- Others remain low priority  

---

## Step 4: Expand Routing
- Convert each component into operation sequence  

---

## Step 5: Assign Machines
- Map operations to machine types  

---

## Step 6: Calculate Machine Load
- Sum operation hours per machine  
- Convert to days  

---

## Step 7: Detect Overload
- Compare load vs buffer  

---

## Step 8: Apply Decision Logic
- Try alternate machine  
- Else evaluate vendor  
- Recommend subcontract if beneficial  

---

## Step 9: Generate Output
- Machine load report  
- Overload alerts  
- Subcontract recommendations  
- Valve readiness  

---

# 5. Key Screens (UI Requirements)

## 5.1 Dashboard
- Total active valves  
- Total value  
- Overloaded machines  
- Alerts  

---

## 5.2 Data Upload
- Upload Excel  
- Validate input  

---

## 5.3 Incoming Load View
- Components expected from fabrication  

---

## 5.4 Machine Load Dashboard
| Machine | Load Days | Buffer | Status |
|--------|----------|--------|--------|

---

## 5.5 Machine Queue Detail
- Job sequence per machine  

---

## 5.6 Subcontract Recommendation
| Component | Valve | Machine | Internal Wait | Vendor Time | Recommendation |

---

## 5.7 Valve Readiness
| Valve | Components Ready | Full Kit | Status |

---

## 5.8 Planner Actions
- Override decisions  
- Change machine assignment  
- Add remarks  

---

## 5.9 Vendor Dashboard
- Pending jobs  
- Oldest job ageing  

---

## 5.10 OTD Risk Dashboard
- Valve delay tracking  
- Root cause  

---

# 6. System Constraints

- Keep logic **rule-based** (no complex optimization in V1)  
- Must be **explainable to planner**  
- Must allow **manual override**  
- Focus on **decision support**, not automation  

---

# 7. Technology Stack

- Backend: Python (FastAPI / Django)  
- Frontend: React  
- Database: PostgreSQL (or simple storage for V1)  

---

# 8. MVP Scope (Version 1)

The system must:

- Read Excel input  
- Calculate machine load  
- Identify overload  
- Recommend subcontracting  
- Show valve readiness  

---

# 9. Success Criteria

The system is successful if:

- Planner can predict next week’s load  
- Overload is identified early  
- Subcontract decisions improve flow  
- OTD improves  

---

# 10. Final Note

This is **Version 1**.

Future improvements may include:
- Optimization algorithms  
- AI-based predictions  
- Better scheduling logic  
- Real-time integration  

---

# 🚀 Instruction for Developer / Claude

Build a simple, functional Version 1 system based on this specification.

Do NOT:
- Overcomplicate  
- Add unnecessary features  
- Build full ERP  

Focus on:
- clarity  
- usability  
- correct planning logic  
```
