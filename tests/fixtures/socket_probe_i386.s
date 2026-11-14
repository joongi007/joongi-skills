.global _start
.section .text
_start:
 mov $102,%eax
 mov $1,%ebx
 mov $socket_args,%ecx
 int $0x80
 cmp $-1,%eax
 je denied
 test %eax,%eax
 js other_error
 mov %eax,%ebx
 mov $6,%eax
 int $0x80
 mov $42,%ebx
 jmp exit
other_error:
 mov $43,%ebx
 jmp exit
denied:
 xor %ebx,%ebx
exit:
 mov $1,%eax
 int $0x80
.section .data
socket_args:
 .long 1,1,0
