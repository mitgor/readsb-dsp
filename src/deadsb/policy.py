"""Per-job bounded reductions; can disable configured branches, never enable one."""
from contextlib import contextmanager

@contextmanager
def reduced(decoder, role, policy):
    level=policy.get('level',0) if policy else 0
    if type(level) is not int or level not in range(5):
        raise ValueError('Invalid CPU admission level')
    changes=[]
    def set_attr(obj,key,value):
        if obj is not None and hasattr(obj,key):
            changes.append((obj,key,getattr(obj,key)));setattr(obj,key,value)
    try:
        if level and role=='coherent':
            d=decoder.decoder
            set_attr(d,'budget',max(1,d.budget//2))
            set_attr(d,'pair_retry',False)
            set_attr(d,'sequence_enabled',False)
            set_attr(d,'acquisition_enabled',False)
        elif level:
            set_attr(decoder,'budget',max(1,decoder.budget//2))
            if level>=2:set_attr(decoder,'neural_enabled',False)
            if level>=3:
                set_attr(decoder,'classical',None)
                set_attr(decoder,'pulse_model',None)
                set_attr(decoder,'broad_crc',False)
            elif level>=2:
                classical=getattr(decoder,'classical',None)
                if classical:set_attr(classical,'stages',tuple(s for s in classical.stages if s in ('soft','timing','matched')))
                set_attr(decoder,'pulse_model',None)
                set_attr(decoder,'broad_crc',False)
        yield level>=4 or (role=='coherent' and level>=2)
    finally:
        for obj,key,value in reversed(changes):setattr(obj,key,value)
