import time
import math
import serial

# --- RS485 ---
PORT='/dev/ttyUSB0'

# ZLTECH - esclavo 1
SLAVE_ID=1
BAUD_ZLTECH=115200

# ESTUN - esclavo 2
SERVO_ID=2
BAUD_SERVO=9600

# --- LLANTAS ---
DIAMETRO_RUEDA_M=0.254
PPR=16384
CIRCUNFERENCIA=math.pi*DIAMETRO_RUEDA_M
PULSOS_POR_METRO=PPR/CIRCUNFERENCIA
DISTANCIA_MOVIMIENTO=0.1
RAMPA_MS=500
VEL_RPM=30

# --- BROCAS ---
SERVO_RPM=500
TIEMPO_BROCAS=5

ser=None

def crc(data):
    c=0xFFFF
    for x in data:
        c^=x
        for _ in range(8):
            c=(c>>1)^0xA001 if c&1 else c>>1
    return c.to_bytes(2,'little')

def rtu(data):
    ser.write(data+crc(data))
    time.sleep(0.05)

def lrc(data):
    return (-sum(data))&255

def ascii_write(addr,value):
    d=bytes([SERVO_ID,6,addr>>8,addr&255,value>>8,value&255])
    f=b":"+d.hex().upper().encode()+f"{lrc(d):02X}".encode()+b"\r\n"
    ser.write(f)
    time.sleep(0.1)

def baud(vel):
    ser.baudrate=vel
    time.sleep(0.1)

def int_a_4bytes(n):
    b=n.to_bytes(4,'big',signed=True)
    return b[:2],b[2:]

# --- LLANTAS ---

def limpiar_errores():
    baud(BAUD_ZLTECH)
    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,6]))
    print("Errores ZLTECH limpiados")

def arrancar_llantas():
    baud(BAUD_ZLTECH)

    pulsos=int(DISTANCIA_MOVIMIENTO*PULSOS_POR_METRO)
    h1,l1=int_a_4bytes(pulsos)
    h2,l2=int_a_4bytes(-pulsos)

    # Sincronizado + relativo
    rtu(bytearray([SLAVE_ID,6,0x20,0x0F,0,1]))
    rtu(bytearray([SLAVE_ID,6,0x20,0x0D,0,1]))

    # Rampas
    r=RAMPA_MS.to_bytes(2,'big')
    for reg in [0x80,0x81,0x82,0x83]:
        rtu(bytearray([SLAVE_ID,6,0x20,reg])+r)

    # Velocidad
    v=VEL_RPM.to_bytes(2,'big')
    rtu(bytearray([SLAVE_ID,6,0x20,0x8E])+v)
    rtu(bytearray([SLAVE_ID,6,0x20,0x8F])+v)

    # Enable
    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,8]))
    time.sleep(0.1)

    # Posición
    trama=bytearray([SLAVE_ID,0x10,0x20,0x8A,0,4,8])
    trama+=h1+l1+h2+l2
    rtu(trama)

    # START
    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,0x10]))

    print("LLANTAS ARRANCADAS")

def frenar_llantas():
    baud(BAUD_ZLTECH)
    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,7]))
    print("LLANTAS DETENIDAS")

# --- ESTUN ---

def arrancar_brocas():
    baud(BAUD_SERVO)

    # 1023h = Servo ON
    ascii_write(0x1023,1)
    time.sleep(0.2)

    # 1024h = JOG adelante
    ascii_write(0x1024,1)

    print("ESTUN JOG ACTIVO - 500 RPM")

def frenar_brocas():
    baud(BAUD_SERVO)

    # 1024h = JOG OFF
    ascii_write(0x1024,0)
    time.sleep(0.2)

    # 1023h = Servo OFF
    ascii_write(0x1023,0)

    print("ESTUN DETENIDO")

def emergencia():
    print("\n!!! PARADA DE EMERGENCIA !!!")
    frenar_brocas()
    frenar_llantas()

def main():
    global ser

    try:
        ser=serial.Serial(PORT,BAUD_ZLTECH,timeout=1)

        print("\n=== PRUEBA MANUAL DE LA MAQUINA ===")
        print("A = Arrancar llantas")
        print("B = Frenar llantas")
        print("P = Arrancar ESTUN")
        print("L = Frenar ESTUN")
        print("C = PARADA DE EMERGENCIA")
        print("Q = Salir")
        print("------------------------------------")
        print("GPIO 10 DESHABILITADO")
        print("GPIO 17, 27 y 22 DESHABILITADOS")
        print("------------------------------------")

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
                print("Programa finalizado")
                break

            else:
                print("Tecla no válida")

    except KeyboardInterrupt:
        print("\nPrograma detenido")

    except Exception as e:
        print("Error:",e)

    finally:
        if ser and ser.is_open:
            try:
                frenar_brocas()
                frenar_llantas()
            except:
                pass
            ser.close()

if __name__=="__main__":
    main()
