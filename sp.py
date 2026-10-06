import serial
import time

PORT='/dev/ttyUSB0'
ID=2

s=serial.Serial(PORT,9600,bytesize=8,parity='O',stopbits=1,timeout=1)

def lrc(d):
    return (-sum(d))&255

def write(reg,val):
    d=bytes([ID,6,reg>>8,reg&255,val>>8,val&255])
    f=b":"+d.hex().upper().encode()+f"{lrc(d):02X}".encode()+b"\r\n"

    print("TX:",f.decode().strip())
    s.write(f)

    r=s.read(50)

    if r:
        print("RX:",r.decode(errors='replace').strip())
        return True

    print("SIN RESPUESTA")
    return False

print("ESTUN - ESCLAVO 2")
print("P = ARRANCAR")
print("L = PARAR")
print("Q = SALIR")

try:
    while True:
        c=input("> ").upper()

        if c=="P":
            print("\nServo ON")
            if write(0x1023,1):
                time.sleep(0.3)

                print("JOG")
                write(0x1024,1)

        elif c=="L":
            print("\nPARAR")
            write(0x1024,0)
            time.sleep(0.3)
            write(0x1023,0)

        elif c=="Q":
            write(0x1024,0)
            time.sleep(0.3)
            write(0x1023,0)
            break

finally:
    s.close()
