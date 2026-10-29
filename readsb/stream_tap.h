/* Nonblocking UC8 copy from readsb's existing sole RTL callback. No decoder changes.
 * Every datagram carries its absolute software sample offset. Drop on congestion;
 * the consumer discards discontinuous windows. Never write I/Q to disk here. */
#ifndef ADSB_RESCUE_STREAM_TAP_H
#define ADSB_RESCUE_STREAM_TAP_H
#include <sys/socket.h>
#include <sys/un.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <stddef.h>
struct __attribute__((packed)) rescue_header {
    char magic[4]; uint32_t epoch, rate, bytes;
    uint64_t sample, unix_ns, dropped;
}; /* little endian, 40 bytes; supported target aarch64 Linux */
static void rescue_stream_samples(const unsigned char *buf, uint32_t len, unsigned rate) {
    static int initialized, fd=-1;
    static uint64_t samples, dropped;
    static struct sockaddr_un address;
    static unsigned char packet[60040];
    uint64_t first=samples; samples+=len/2;
    if (!initialized) {
        initialized=1;
        const char *path=getenv("ADSB_RESCUE_SOCKET");
        if (!path || strncmp(path,"/run/",5) || strlen(path)>=sizeof address.sun_path) return;
        fd=socket(AF_UNIX,SOCK_DGRAM,0);
        if(fd<0) return;
        if(fcntl(fd,F_SETFL,O_NONBLOCK)<0 || fcntl(fd,F_SETFD,FD_CLOEXEC)<0) {close(fd);fd=-1;return;}
        address.sun_family=AF_UNIX;strcpy(address.sun_path,path);
        int size=1024*1024;setsockopt(fd,SOL_SOCKET,SO_SNDBUF,&size,sizeof size);
    }
    if(fd<0 || rate!=2400000 || (len&1)) return;
    struct timespec now;clock_gettime(CLOCK_REALTIME,&now);
    uint64_t ns=(uint64_t)now.tv_sec*1000000000ULL+now.tv_nsec;
    for(uint32_t offset=0;offset<len;) {
        uint32_t n=len-offset;if(n>60000)n=60000;
        struct rescue_header h={{'R','S','C','1'},(uint32_t)getpid(),rate,n,
            first+offset/2,ns+(uint64_t)(offset/2)*1000000000ULL/rate,dropped};
        memcpy(packet,&h,sizeof h);memcpy(packet+sizeof h,buf+offset,n);
        if(sendto(fd,packet,sizeof h+n,MSG_DONTWAIT|MSG_NOSIGNAL,
                (struct sockaddr*)&address,sizeof address)!=(ssize_t)(sizeof h+n)) {
            dropped+=(len-offset)/2;break;
        }
        offset+=n;
    }
}
#endif
