/* Exact policy orchestration. Frozen header/energy arithmetic is included verbatim.
 * Ranking values stay in NumPy: complex abs/reduction rounding is platform-specific.
 * No fast-math, RF I/O, CRC admission or search-budget changes. */
#include "frontend.c"
int64_t rescue_acq_screen(const float *iq,int64_t length,const int64_t *normal,int64_t n,int64_t *pending,int64_t *ordinary){
 if(length<0||n<0||n>1000000)return -1;
 int64_t count=0;*ordinary=0;
 for(int64_t j=0;j<n;j++){
  int64_t s=normal[j],id;uint8_t row[14],valid;
  if(s<8||length<489||s>=length-488)continue;
  if(!rescue_header_ids(iq,&s,1,&id))continue;
  (*ordinary)++;rescue_baseline(iq,&s,1,row,&valid);
  if(!valid)pending[count++]=s;
 }
 return count;
}
/* Stable descending top-k; equal values retain original candidate order. */
int64_t rescue_acq_top(const int64_t *starts,const double *rank,int64_t n,int64_t budget,int64_t *out){
 if(n<0||n>1000000||budget<0||budget>4096)return -1;
 for(int64_t j=0;j<n;j++)if(!isfinite(rank[j]))return -1;
 int64_t count=0,ids[4096];
 for(int64_t j=0;j<n;j++){
  int64_t k=count;
  if(k==budget){if(!budget||rank[j]<=rank[ids[k-1]])continue;k--;}
  while(k>0&&rank[j]>rank[ids[k-1]]){ids[k]=ids[k-1];k--;}
  ids[k]=j;if(count<budget)count++;
 }
 for(int64_t j=0;j<count;j++)out[j]=starts[ids[j]];
 return count;
}
int64_t rescue_acq_union(const int64_t *pending,int64_t np,const int64_t *acquire,int64_t na,int64_t *starts,int64_t *pi,int64_t *ai){
 if(np<0||na<0||np+na>8192)return -1;
 int64_t count=0;
 for(int64_t j=0;j<np+na;j++){
  int64_t s=j<np?pending[j]:acquire[j-np],k=count;
  while(k>0&&starts[k-1]>s){starts[k]=starts[k-1];k--;}
  if(k>0&&starts[k-1]==s){/* Undo right shifts after a duplicate. */
   for(int64_t q=k;q<count;q++)starts[q]=starts[q+1];continue;
  }
  starts[k]=s;count++;
 }
 for(int64_t j=0;j<np;j++){int64_t k=0;while(k<count&&starts[k]!=pending[j])k++;pi[j]=k;}
 for(int64_t j=0;j<na;j++){int64_t k=0;while(k<count&&starts[k]!=acquire[j])k++;ai[j]=k;}
 return count;
}
