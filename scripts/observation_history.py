"""Causal frame history, in the same oldest-to-newest order as the SDK."""
class ObservationHistory:
    def __init__(self,frames=1,width=48):
        if frames not in (1,3,5) or width<1:raise ValueError('Unsupported observation history')
        self.frames,self.width=frames,width;self.values=None
    def reset(self,x):
        if len(x)!=self.width:raise ValueError('Observation width differs')
        self.values=list(x)*self.frames;return self.values
    def push(self,x):
        if self.values is None:return self.reset(x)
        if len(x)!=self.width:raise ValueError('Observation width differs')
        self.values=self.values[self.width:]+list(x);return self.values

def schema_suffix(frames):
    if frames not in (1,3,5):raise ValueError('Unsupported history')
    return '' if frames==1 else f'|history={frames}'
