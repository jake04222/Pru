import time
import math
import serial

PORT='/dev/ttyUSB0'

# ZLTECH
SLAVE_ID=1
BAUD_ZLTECH=115200

# ESTUN
SERVO_ID=2
BAUD_SERVO=9600

# Llantas
DIAMETRO_RUEDA_M=0.254
PPR=16384
CIRCUNFERENCIA=math.pi*DIAMETRO_RUEDA_M
PULSOS_POR_METRO=PPR/CIRCUNFERENCIA
DISTANCIA_MOVIMIENTO=0.1
RAMPA_MS=500
VEL_RPM=30

# Brocas
TIEMPO_BROCAS=5

ser=None

def abrir_puerto(baudrate,parity='N'):
    global ser

    if ser and ser.is_open:
        ser.close()
        time.sleep(0.2)

    ser=serial.Serial(
        PORT,
        baudrate,
        bytesize=8,
        parity=parity,
        stopbits=1,
        timeout=1
    )

    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

def crc(data):
    c=0xFFFF
    for x in data:
        c^=x
        for _ in range(8):
            c=(c>>1)^0xA001 if c&1 else c>>1
    return c.to_bytes(2,'little')

def rtu(data):
    ser.write(data+crc(data))
    ser.flush()
    time.sleep(0.1)

def lrc(data):
    return (-sum(data))&255

def ascii_write(reg,val):
    d=bytes([
        SERVO_ID,6,
        reg>>8,reg&255,
        val>>8,val&255
    ])

    f=b":"+d.hex().upper().encode()
    f+=f"{lrc(d):02X}".encode()
    f+=b"\r\n"

    print("TX:",f.decode().strip())

    ser.write(f)
    ser.flush()
    time.sleep(0.15)

    r=ser.read(50)

    if r:
        print("RX:",r.decode(errors='replace').strip())
        return True

    print("SIN RESPUESTA")
    return False

def int_a_4bytes(n):
    b=n.to_bytes(4,'big',signed=True)
    return b[:2],b[2:]

# ---------------- LLANTAS ----------------

def arrancar_llantas():
    abrir_puerto(BAUD_ZLTECH)

    pulsos=int(DISTANCIA_MOVIMIENTO*PULSOS_POR_METRO)
    h1,l1=int_a_4bytes(pulsos)
    h2,l2=int_a_4bytes(-pulsos)

    rtu(bytearray([SLAVE_ID,6,0x20,0x0F,0,1]))
    rtu(bytearray([SLAVE_ID,6,0x20,0x0D,0,1]))

    r=RAMPA_MS.to_bytes(2,'big')

    for reg in [0x80,0x81,0x82,0x83]:
        rtu(bytearray([SLAVE_ID,6,0x20,reg])+r)

    v=VEL_RPM.to_bytes(2,'big')

    rtu(bytearray([SLAVE_ID,6,0x20,0x8E])+v)
    rtu(bytearray([SLAVE_ID,6,0x20,0x8F])+v)

    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,8]))

    time.sleep(0.1)

    trama=bytearray([
        SLAVE_ID,0x10,
        0x20,0x8A,
        0,4,8
    ])

    trama+=h1+l1+h2+l2

    rtu(trama)

    rtu(bytearray([
        SLAVE_ID,6,
        0x20,0x0E,
        0,0x10
    ]))

    print("LLANTAS ARRANCADAS")

def frenar_llantas():
    abrir_puerto(BAUD_ZLTECH)

    rtu(bytearray([
        SLAVE_ID,6,
        0x20,0x0E,
        0,7
    ]))

    print("LLANTAS DETENIDAS")

# ---------------- ESTUN ----------------

def arrancar_brocas():
    abrir_puerto(BAUD_SERVO,'O')

    print("ESTUN: SERVO ON")

    if not ascii_write(0x1023,1):
        print("ERROR: ESTUN no respondió a SERVO ON")
        return False

    time.sleep(0.3)

    print("ESTUN: JOG")

    if not ascii_write(0x1024,1):
        print("ERROR: ESTUN no respondió a JOG")
        return False

    print("BROCAS ARRANCADAS - 500 RPM")
    return True

def frenar_brocas():
    abrir_puerto(BAUD_SERVO,'O')

    ascii_write(0x1024,0)

    time.sleep(0.3)

    ascii_write(0x1023,0)

    print("BROCAS DETENIDAS")

# ---------------- EMERGENCIA ----------------

def emergencia():
    print("\n!!! PARADA !!!")

    frenar_brocas()
    frenar_llantas()

# ---------------- PRINCIPAL ----------------

def main():
    global ser

    try:
        print("\n=== PRUEBA MAQUINA ===")
        print("A = Arrancar llantas")
        print("B = Frenar llantas")
        print("P = Arrancar ESTUN")
        print("L = Frenar ESTUN")
        print("C = Parada")
        print("Q = Salir")
        print("----------------------")

        while True:

            tecla=input("> ").strip().upper()

            if tecla=="A":
                arrancar_llantas()

            elif tecla=="B":
                frenar_llantas()

            elif tecla=="P":
                arrancar_brocas()

            elif tecla=="L":
                frenar_brocas()

            elif tecla=="C":
                emergencia()

            elif tecla=="Q":
                emergencia()
                break

            else:
                print("Tecla no válida")

    except KeyboardInterrupt:
        print("\nPrograma detenido")

    except Exception as e:
        print("\nERROR:",e)

    finally:
        try:
            frenar_brocas()
        except:
            pass

        try:
            frenar_llantas()
        except:
            pass

        if ser and ser.is_open:
            ser.close()

if __name__=="__main__":
    main()
