"""Persistent native evaluator; uses the existing physical perturbation protocol."""
import json
from pathlib import Path
import queue
import subprocess
import threading
from run_fast_ppo import ROOT,steam_packs


class Evaluator:
    def __init__(self,output,library=None,track=None):
        self.output=Path(output);self.messages=queue.Queue();self.sequence=0
        self.log=Path(str(self.output)+'.stderr.log').open('x')
        cmd=[ROOT/'native/build-linux/tm2020_generalist_train','--mode','eval-stream','--output',self.output,
             '--library',library or ROOT/'cache/reward-study-target/release/libtm2020_speed.so',
             '--map',track or ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx',
             '--packs',steam_packs(),'--route','/dev/null','--actions',1,'--planner',0,'--horizon',4000]
        self.child=subprocess.Popen(list(map(str,cmd)),cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                    stderr=self.log,text=True,bufsize=1)
        def reader():
            for line in self.child.stdout:self.messages.put(line.rstrip('\n'))
            self.messages.put(None)
        self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()
        self.wait('EVAL_STREAM_READY',timeout=180)

    def wait(self,prefix,timeout=180):
        while True:
            try:line=self.messages.get(timeout=timeout)
            except queue.Empty:raise TimeoutError(f'Native evaluator timed out; see {self.log.name}')
            if line is None:raise RuntimeError(f'Native evaluator exited: {self.child.poll()}; see {self.log.name}')
            if line.startswith(prefix):return line[len(prefix):]

    def evaluate(self,model,trials=5,seed=921042):
        path=str(Path(model).resolve(strict=True))
        if '\n' in path:raise ValueError('Invalid model path')
        self.child.stdin.write(f'TM2020_EVAL_V1\n{path}\n{trials}\n{seed}\n');self.child.stdin.flush()
        result=json.loads(self.wait('EVAL_JSON '))
        if result['sequence']!=self.sequence:raise ValueError('Evaluation sequence differs')
        self.sequence+=1;return result['candidate']

    def close(self):
        if self.child.poll() is None:
            try:self.child.stdin.write('STOP\n');self.child.stdin.flush();self.child.wait(timeout=10)
            except (BrokenPipeError,subprocess.TimeoutExpired):self.child.terminate();self.child.wait(timeout=5)
        self.child.stdin.close();self.child.stdout.close();self.log.close()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
