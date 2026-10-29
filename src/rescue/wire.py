"""Incremental Beast parser. Preserve incomplete/escaped records across TCP reads."""
class BeastParser:
    def __init__(self,preserve_wire=False):self.buffer=bytearray();self.preserve_wire=preserve_wire
    def feed(self,chunk):
        self.buffer.extend(chunk);data=self.buffer;out=[];i=0;lengths={0x31:9,0x32:14,0x33:21}
        while i+1<len(data):
            if data[i]!=26:i+=1;continue
            kind=data[i+1]
            if kind not in lengths:i+=2;continue
            j=i+2;body=bytearray();bad=False;incomplete=False
            while len(body)<lengths[kind]:
                if j>=len(data):incomplete=True;break
                b=data[j]
                if b==26:
                    if j+1>=len(data):incomplete=True;break
                    if data[j+1]!=26:bad=True;break
                    j+=1
                body.append(b);j+=1
            if incomplete:break
            if bad:i=max(i+1,j);continue
            row=dict(ticks_12mhz=int.from_bytes(body[:6],'big'),message_hex=body[7:].hex(),signal_byte=body[6],kind=kind)
            if self.preserve_wire:row['wire_hex']=bytes(data[i:j]).hex()
            out.append(row);i=j
        del data[:i]
        if len(data)>256:raise ValueError('Unbounded Beast partial record')
        return out
