# Module — TrustSec policy (SGTs + SGACLs + authZ) in ISE

Built directly in ISE (source of truth). Employees(4)/Contractors(5) are default SGTs; add the
rest. `curl` against ERS/OpenAPI (MCP body params get JSON-coerced).

## SGTs
```bash
# free values 16+ (defaults use 0,2-15,255):  ise_create_sgt
IoT = 100    Shared_Services = 200
```

## SGACL + egress matrix
```bash
# custom SGACL (ERS POST /ers/config/sgacl), aclcontent newline-separated ACEs:
{"Sgacl":{"name":"SDA_Web_Permit","ipVersion":"IPV4",
  "aclcontent":"permit icmp\npermit tcp dst eq 443\npermit tcp dst eq 80\ndeny ip"}}
# egress cells (ERS POST /ers/config/egressmatrixcell), one per src→dst:
#   Employees(4)   → Shared_Services(200) : [SDA_Web_Permit]
#   Contractors(5) → Shared_Services(200) : [Deny_IP_Log]
#   IoT(100)       → Shared_Services(200) : [Deny_IP_Log]
{"EgressMatrixCell":{"name":"Employees_to_SharedSvc","sourceSgtId":"<4>","destinationSgtId":"<200>",
  "matrixCellStatus":"ENABLED","defaultRule":"NONE","sgacls":["<SDA_Web_Permit id>"]}}
```

## Policy set `SDA_Wired` (OpenAPI /api/v1/policy/network-access)
```bash
# create the set — condition = OR of the built-in Wired_802.1X + Wired_MAB library refs:
{"name":"SDA_Wired","serviceName":"Default Network Access","state":"enabled","rank":0,"isProxy":false,
 "condition":{"conditionType":"ConditionOrBlock","children":[
   {"conditionType":"ConditionReference","id":"58f909ca-…","name":"Wired_802.1X"},
   {"conditionType":"ConditionReference","id":"36052685-…","name":"Wired_MAB"}]}}
# authentication default rule → PUT …/{ps}/authentication/{id}:
{"rule":{"default":true,"id":"…","name":"Default","rank":0,"state":"enabled","condition":null},
 "identitySourceName":"AD_Internal_Seq","ifAuthFail":"REJECT","ifUserNotFound":"CONTINUE","ifProcessFail":"DROP"}
# authorization rules (POST …/{ps}/authorization), each profile:["PermitAccess"] + securityGroup:
#   Employees_SGT  : ConditionAttributes dict "mitchcloud" attr ExternalGroups = mitchcloud.lab/Users/Employees  → Employees
#   Contractors_SGT: … mitchcloud.lab/Users/Contractors → Contractors
#   IoT_MAB        : ConditionReference Wired_MAB → IoT
#   Default        : DenyAccess  (Closed Auth)
```
- `ifUserNotFound=CONTINUE` is essential: dot1x resolves against AD, and unknown-MAC MAB
  falls through to the authorization rules instead of being rejected.
- The AD-group condition dictionary name = the **join-point name** (`mitchcloud`), attribute
  `ExternalGroups`, value `<domain>/<container>/<Group>`.
- CatC reads these SGTs over pxGrid; no need to author them in CatC.
