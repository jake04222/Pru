import time
import math
import serial
import threading
import RPi.GPIO as GPIO

PORT='/dev/ttyUSB0'

SLAVE_ID=1
BAUD_ZLTECH=115200
SERVO_ID=2
BAUD_SERVO=9600

GPIO_START=17
GPIO_STOP=27
GPIO_EMERGENCY=22
GPIO_EMERGENCY_OUT=10

GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO_START,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_STOP,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_EMERGENCY,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_EMERGENCY_OUT,GPIO.OUT,initial=GPIO.HIGH)

DIAMETRO_RUEDA_M=0.254
PPR=16384
CIRCUNFERENCIA=math.pi*DIAMETRO_RUEDA_M
PULSOS_POR_METRO=PPR/CIRCUNFERENCIA
DISTANCIA_MOVIMIENTO=0.5
RAMPA_MS=500
VEL_RPM=30
TIEMPO_BROCAS=5
TIEMPO_PARO=2

ser=None
estado='PARADA'
emergencia_activa=False
paro_event=threading.Event()
emergencia_event=threading.Event()
arranque_event=threading.Event()
lock=threading.Lock()

def monitor():
    inicio_paro=None
    anterior_arranque=GPIO.input(GPIO_START)

    while True:
        if GPIO.input(GPIO_EMERGENCY)==GPIO.HIGH:
            emergencia_event.set()

        if GPIO.input(GPIO_STOP)==GPIO.LOW:
            if inicio_paro is None:
                inicio_paro=time.monotonic()
            elif time.monotonic()-inicio_paro>=TIEMPO_PARO:
                paro_event.set()
        else:
            inicio_paro=None

        actual=GPIO.input(GPIO_START)
        if anterior_arranque==GPIO.HIGH and actual==GPIO.LOW:
            arranque_event.set()
        anterior_arranque=actual
        time.sleep(0.01)

def abrir_puerto(baudrate,parity='N'):
    global ser
    if ser and ser.is_open:
        ser.close()
    ser=serial.Serial(PORT,baudrate,bytesize=8,parity=parity,
                      stopbits=1,timeout=0.1,write_timeout=0.1)
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
    if emergencia_event.is_set() or paro_event.is_set():
        return False
    ser.write(data+crc(data))
    ser.flush()
    time.sleep(0.01)
    return not emergencia_event.is_set() and not paro_event.is_set()

def lrc(data):
    return (-sum(data))&255

def ascii_write(reg,val):
    if emergencia_event.is_set() or paro_event.is_set():
        return False
    d=bytes([SERVO_ID,6,reg>>8,reg&255,val>>8,val&255])
    f=b":"+d.hex().upper().encode()+f"{lrc(d):02X}".encode()+b"\r\n"
    ser.write(f)
    ser.flush()
    time.sleep(0.02)
    return bool(ser.read(50)) and not emergencia_event.is_set() and not paro_event.is_set()

def int_a_4bytes(n):
    b=n.to_bytes(4,'big',signed=True)
    return b[:2],b[2:]

def arrancar_llantas():
    abrir_puerto(BAUD_ZLTECH)
    pulsos=int(DISTANCIA_MOVIMIENTO*PULSOS_POR_METRO)
    h1,l1=int_a_4bytes(pulsos)
    h2,l2=int_a_4bytes(-pulsos)

    comandos=[
        bytearray([SLAVE_ID,6,0x20,0x0F,0,1]),
        bytearray([SLAVE_ID,6,0x20,0x0D,0,1])
    ]
    r=RAMPA_MS.to_bytes(2,'big')
    comandos += [bytearray([SLAVE_ID,6,0x20,reg])+r
                 for reg in [0x80,0x81,0x82,0x83]]
    v=VEL_RPM.to_bytes(2,'big')
    comandos += [
        bytearray([SLAVE_ID,6,0x20,0x8E])+v,
        bytearray([SLAVE_ID,6,0x20,0x8F])+v,
        bytearray([SLAVE_ID,6,0x20,0x0E,0,8])
    ]
    trama=bytearray([SLAVE_ID,0x10,0x20,0x8A,0,4,8])+h1+l1+h2+l2
    comandos.append(trama)
    comandos.append(bytearray([SLAVE_ID,6,0x20,0x0E,0,0x10]))

    for cmd in comandos:
        if not rtu(cmd):
            return False
    print("LLANTAS: MOVIMIENTO")
    return True

def frenar_llantas():
    abrir_puerto(BAUD_ZLTECH)
    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,7]))
    print("LLANTAS: PARADAS")

def arrancar_brocas():
    abrir_puerto(BAUD_SERVO,'O')
    if not ascii_write(0x1023,1):
        return False
    if not ascii_write(0x1024,1):
        return False
    print("ESTUN: ENCENDIDO")
    return True

def frenar_brocas():
    abrir_puerto(BAUD_SERVO,'O')
    ascii_write(0x1024,0)
    ascii_write(0x1023,0)
    print("ESTUN: PARADO")

def detener():
    global estado
    estado='PARADA'
    print("PARANDO MAQUINA")
    try:
        frenar_brocas()
    except Exception as e:
        print("Error parando brocas:",e)
    try:
        frenar_llantas()
    except Exception as e:
        print("Error parando llantas:",e)

def emergencia():
    global estado,emergencia_activa
    emergencia_activa=True
    estado='PARADA'
    GPIO.output(GPIO_EMERGENCY_OUT,GPIO.LOW)
    print("!!! EMERGENCIA !!!")
    detener()

def orden_parada():
    if emergencia_event.is_set():
        emergencia()
        return True
    if paro_event.is_set():
        detener()
        return True
    return False

def esperar(tiempo):
    fin=time.monotonic()+tiempo
    while time.monotonic()<fin:
        if orden_parada():
            return False
        time.sleep(0.01)
    return not orden_parada()

def ciclo():
    global estado,emergencia_activa
    estado='MARCHA'
    emergencia_activa=False
    paro_event.clear()
    arranque_event.clear()
    GPIO.output(GPIO_EMERGENCY_OUT,GPIO.HIGH)
    print("MAQUINA EN MARCHA")

    while estado=='MARCHA':
        if orden_parada():
            break

        tiempo_mov=DISTANCIA_MOVIMIENTO/(VEL_RPM*CIRCUNFERENCIA/60)

        if not arrancar_llantas():
            if orden_parada():
                break
            continue

        if not esperar(tiempo_mov):
            break

        frenar_llantas()
        if orden_parada():
            break

        if not arrancar_brocas():
            if orden_parada():
                break
            detener()
            break

        if not esperar(TIEMPO_BROCAS):
            break

        frenar_brocas()
        if orden_parada():
            break

        print("REPITIENDO CICLO")

    if estado!='PARADA':
        detener()
    print("MAQUINA DETENIDA")

def main():
    global estado
    threading.Thread(target=monitor,daemon=True).start()

    print("GPIO17: ARRANQUE")
    print("GPIO27: PARO (mantener 2 s)")
    print("GPIO22: EMERGENCIA NC")
    print("GPIO10: SALIDA EMERGENCIA")

    try:
        while True:
            if orden_parada():
                time.sleep(0.05)
                continue

            if arranque_event.is_set() and estado=='PARADA':
                arranque_event.clear()
                if not emergencia_event.is_set():
                    paro_event.clear()
                    ciclo()

            time.sleep(0.01)

    except KeyboardInterrupt:
        emergencia()
    except Exception as e:
        print("ERROR:",e)
        emergencia()
    finally:
        try:
            emergencia()
        finally:
            GPIO.cleanup()
            if ser and ser.is_open:
                ser.close()

if __name__=="__main__":
    main()
