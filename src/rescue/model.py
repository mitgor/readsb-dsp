"""Bit-resolution residual CNN: phase channels preserve four samples per bit."""
import torch
from torch import nn

class TinyDecoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.entry = nn.Conv1d(8, 12, 5, padding=2)
        self.blocks = nn.ModuleList([
            nn.Sequential(nn.Conv1d(12, 12, 5, padding=2*d, dilation=d, groups=12),
                          nn.ReLU(), nn.Conv1d(12, 12, 1)) for d in (1, 3)])
        self.out = nn.Conv1d(12, 1, 1)
        # Start at the conventional slicer and learn corrections.
        nn.init.zeros_(self.out.weight)
        nn.init.zeros_(self.out.bias)

    def forward(self, x):
        # N,2,480 -> N,8,120. Temporal position is one ADS-B bit.
        phases = x.reshape(-1, 2, 120, 4).permute(0, 1, 3, 2).reshape(-1, 8, 120)
        h = torch.relu(self.entry(phases))
        for block in self.blocks:
            h = torch.relu(h + block(h))
        p = x[:, 0, 32:].reshape(-1, 112, 4)
        conventional = (p[:, :, :2].sum(-1) - p[:, :, 2:].sum(-1))*3
        return conventional + self.out(h).squeeze(1)[:, 8:]
