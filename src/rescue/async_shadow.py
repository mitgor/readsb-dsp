"""Default asynchronous coordinator; legacy grouping serves statistics only."""
from .shadow import main
if __name__=='__main__':main(asynchronous=True)
