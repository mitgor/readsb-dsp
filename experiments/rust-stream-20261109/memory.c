// SPDX-License-Identifier: GPL-3.0-or-later
// Small exec/fork launcher avoids Python's inherited Linux launch RSS high-water.
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <unistd.h>
#include <stdio.h>
int main(int argc,char**argv){if(argc<3)return 2;pid_t p=fork();if(p<0)return 3;if(p==0){execv(argv[2],argv+2);_exit(127);}int status;struct rusage r;if(wait4(p,&status,0,&r)<0)return 4;FILE*f=fopen(argv[1],"w");if(!f)return 5;fprintf(f,"%ld\n",r.ru_maxrss);fclose(f);return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);}
