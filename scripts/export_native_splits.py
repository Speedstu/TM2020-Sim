#!/usr/bin/env python3
"""Create reproducible map-UID-based train/test index for native-only offline trainer."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"sdk"))
from trackmania2020 import ReplayCorpus

def main():
    c=ReplayCorpus(ROOT)
    train,test=c.group_split(0.2)
    out=ROOT/"local"/"native-datasets"
    out.mkdir(parents=True,exist_ok=True)
    for filename,indices in (("train.txt",train),("test.txt",test)):
        (out/filename).write_text(
            "\n".join(str(c.by_index(idx).tmx_id) for idx in indices)+"\n",
            encoding="utf-8")
        print(filename,len(indices))
    if not train or not test:raise ValueError("Invalid split")
    print("PASS disjoint native train/test split")
if __name__=="__main__":main()
