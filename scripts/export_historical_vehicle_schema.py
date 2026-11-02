#!/usr/bin/env python3
"""Historical vehicle field name/type catalog for OFFLINE Trackmania2020 RE.

Reads existing locally archived Openplanet historical type metadata as a
reference document ONLY. Does NOT install/load/invoke Openplanet in the game.
Indices in the schema are reflection member IDs, NOT struct byte offsets.
"""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
TYPES=ROOT/"references/openplanet-lsp-source/tests/fixtures/typedb-versions/1.29.14/OpenplanetNext.json"
TARGET=ROOT/"local/recon/historical-vehicle-fields.json"

def main():
    source=json.loads(TYPES.read_text(encoding="utf-8-sig"))
    wanted={
        "Scene":["CSceneVehicleVisState"],
        "Game":["CGameCtnChallengeInfo","CGamePlaygroundClientScriptAPI"]
    }
    classes=[]
    for ns,names in wanted.items():
        for name in names:
            data=source["ns"][ns][name]
            fields=[]
            for f in data["m"]:
                if not isinstance(f,dict):continue
                fields.append({
                    "name":f.get("n"),"reflectionIndex":f.get("i"),
                    "type":f.get("t"),"range":f.get("r")
                })
            classes.append({"namespace":ns,"class":name,
                            "historicalObjectSize":data.get("s"),
                            "fields":fields})
    target={
        "schema":"tm2020_historical_vehicle_class_fields_v1",
        "historicalTypeDb":"Openplanet 1.29.14, metadata dated 2026-02-03",
        "usedAsStaticReferenceOnly":True,
        "exact2026OctGameCompatibilityConfirmed":False,
        "byteOffsetsAvailable":False,
        "memoryPointersAvailable":False,
        "actual2026GameStructureValidated":False,
        "notes":"Reflection i is a member identifier, NEVER use as byte offset. No Openplanet runtime dependency.",
        "classes":classes
    }
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    TARGET.write_text(json.dumps(target,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for c in classes:
        print("TYPE",c["class"],"historical members",len(c["fields"]),
              "sizeLabel",c["historicalObjectSize"])
    print("SAVED",TARGET)
if __name__=="__main__":sys.exit(main())
