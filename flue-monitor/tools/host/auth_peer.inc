static int fake_getpeername(int fd,struct sockaddr *out,socklen_t *n) {
 if(!fd)return -1;
 if(fd==3 || fd==4){struct sockaddr_in6 *p=(struct sockaddr_in6 *)out;p->sin6_family=AF_INET6;inet_pton(AF_INET6,fd==3?"::ffff:192.168.1.34":"::ffff:127.0.0.1",&p->sin6_addr);*n=sizeof *p;return 0;}
 struct sockaddr_in *p=(struct sockaddr_in *)out;p->sin_family=AF_INET;p->sin_addr.s_addr=htonl(fd==1?0x7f000001:0xc0a80122);*n=sizeof *p;return 0;
}
