/* Workspace-only variant: identical peak comparison, sorting and masking. */
#include "pipeline_v3.c"
size_t rescue_peak_workspace_bytes(int64_t n){return n>0&&n<=10000000?(size_t)n*sizeof(Peak):0;}
int64_t rescue_buffered_peaks(const double *score,int64_t n,double threshold,int64_t *out,void *workspace,uint8_t *masked){
 if(n<3||n>10000000||!workspace||!masked)return -1;
 Peak *peaks=workspace;memset(masked,0,n);int64_t count=0;
 for(int64_t j=1;j<n-1;j++)if(score[j]>=threshold&&score[j]>score[j-1]){
  int64_t end=j;while(end+1<n&&score[end+1]==score[j])end++;
  if(end<n-1&&score[end]>score[end+1])peaks[count++]=(Peak){score[j],(j+end)/2};j=end;
 }
 qsort(peaks,count,sizeof(Peak),by_score);
 for(int64_t j=1;j<count;j++)if(peaks[j].score==peaks[j-1].score)return -2;
 int64_t keep=0;
 for(int64_t j=0;j<count;j++){
  int64_t pos=peaks[j].position;if(masked[pos])continue;
  for(int t=-2;t<=2;t++)if(pos+t>=0&&pos+t<n)masked[pos+t]=1;
  peaks[keep++]=peaks[j];
 }
 qsort(peaks,keep,sizeof(Peak),by_position);
 for(int64_t j=0;j<keep;j++)out[j]=peaks[j].position;
 return keep;
}
