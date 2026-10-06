# import time
# import math
# import serial
# import RPi.GPIO as GPIO
# import select
# import sys

# PORT='/dev/ttyUSB0'

# # ZLTECH
# SLAVE_ID=1
# BAUD_ZLTECH=115200

# # ESTUN
# SERVO_ID=2
# BAUD_SERVO=9600

# # GPIO
# GPIO_START=17
# GPIO_STOP=27

# GPIO.setmode(GPIO.BCM)
# GPIO.setup(GPIO_START,GPIO.IN,pull_up_down=GPIO.PUD_UP)
# GPIO.setup(GPIO_STOP,GPIO.IN,pull_up_down=GPIO.PUD_UP)

# # Llantas
# DIAMETRO_RUEDA_M=0.254
# PPR=16384
# CIRCUNFERENCIA=math.pi*DIAMETRO_RUEDA_M
# PULSOS_POR_METRO=PPR/CIRCUNFERENCIA
# DISTANCIA_MOVIMIENTO=0.1
# RAMPA_MS=500
# VEL_RPM=30

# # Brocas
# TIEMPO_BROCAS=5

# ser=None
# estado='PARADA'
# emergencia_activa=False

# def abrir_puerto(baudrate,parity='N'):
#     global ser

#     if ser and ser.is_open:
#         ser.close()
#         time.sleep(0.2)

#     ser=serial.Serial(
#         PORT,
#         baudrate,
#         bytesize=8,
#         parity=parity,
#         stopbits=1,
#         timeout=1
#     )

#     time.sleep(0.2)
#     ser.reset_input_buffer()
#     ser.reset_output_buffer()

# def crc(data):
#     c=0xFFFF
#     for x in data:
#         c^=x
#         for _ in range(8):
#             c=(c>>1)^0xA001 if c&1 else c>>1
#     return c.to_bytes(2,'little')

# def rtu(data):
#     ser.write(data+crc(data))
#     ser.flush()
#     time.sleep(0.1)

# def lrc(data):
#     return (-sum(data))&255

# def ascii_write(reg,val):
#     d=bytes([
#         SERVO_ID,6,
#         reg>>8,reg&255,
#         val>>8,val&255
#     ])

#     f=b":"+d.hex().upper().encode()
#     f+=f"{lrc(d):02X}".encode()
#     f+=b"\r\n"

#     ser.write(f)
#     ser.flush()
#     time.sleep(0.15)

#     return bool(ser.read(50))

# def int_a_4bytes(n):
#     b=n.to_bytes(4,'big',signed=True)
#     return b[:2],b[2:]

# # LLANTAS

# def arrancar_llantas():
#     abrir_puerto(BAUD_ZLTECH)

#     pulsos=int(DISTANCIA_MOVIMIENTO*PULSOS_POR_METRO)
#     h1,l1=int_a_4bytes(pulsos)
#     h2,l2=int_a_4bytes(-pulsos)

#     rtu(bytearray([SLAVE_ID,6,0x20,0x0F,0,1]))
#     rtu(bytearray([SLAVE_ID,6,0x20,0x0D,0,1]))

#     r=RAMPA_MS.to_bytes(2,'big')

#     for reg in [0x80,0x81,0x82,0x83]:
#         rtu(bytearray([SLAVE_ID,6,0x20,reg])+r)

#     v=VEL_RPM.to_bytes(2,'big')

#     rtu(bytearray([SLAVE_ID,6,0x20,0x8E])+v)
#     rtu(bytearray([SLAVE_ID,6,0x20,0x8F])+v)

#     rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,8]))

#     trama=bytearray([
#         SLAVE_ID,0x10,
#         0x20,0x8A,
#         0,4,8
#     ])

#     trama+=h1+l1+h2+l2
#     rtu(trama)

#     rtu(bytearray([
#         SLAVE_ID,6,
#         0x20,0x0E,
#         0,0x10
#     ]))

#     print("LLANTAS: 10 cm")

# def frenar_llantas():
#     abrir_puerto(BAUD_ZLTECH)

#     rtu(bytearray([
#         SLAVE_ID,6,
#         0x20,0x0E,
#         0,7
#     ]))

#     print("LLANTAS: PARADAS")

# # ESTUN

# def arrancar_brocas():
#     abrir_puerto(BAUD_SERVO,'O')

#     if not ascii_write(0x1023,1):
#         print("ERROR ESTUN")
#         return False

#     time.sleep(0.3)

#     if not ascii_write(0x1024,1):
#         print("ERROR JOG")
#         return False

#     print("ESTUN: 5 segundos")
#     return True

# def frenar_brocas():
#     abrir_puerto(BAUD_SERVO,'O')

#     ascii_write(0x1024,0)

#     time.sleep(0.3)

#     ascii_write(0x1023,0)

#     print("ESTUN: PARADO")

# # LECTURA DE TERMINAL Y GPIO

# def leer_entradas():
#     global emergencia_activa

#     # Terminal sin bloquear
#     if select.select([sys.stdin],[],[],0)[0]:
#         tecla=sys.stdin.readline().strip().upper()

#         if tecla=='A':
#             return 'START'

#         if tecla=='B':
#             return 'STOP'

#         if tecla=='P':
#             emergencia_activa=True
#             return 'EMERGENCY'

#         if tecla=='Q':
#             emergencia_activa=True
#             return 'QUIT'

#     # GPIO 17 = START
#     if GPIO.input(GPIO_START)==GPIO.LOW:
#         time.sleep(0.05)

#         if GPIO.input(GPIO_START)==GPIO.LOW:
#             return 'START'

#     # GPIO 27 = STOP
#     if GPIO.input(GPIO_STOP)==GPIO.LOW:
#         time.sleep(0.05)

#         if GPIO.input(GPIO_STOP)==GPIO.LOW:
#             return 'STOP'

#     return None

# # EMERGENCIA

# def emergencia():
#     global emergencia_activa

#     emergencia_activa=True

#     print("\n!!! PARADA DE EMERGENCIA !!!")

#     try:
#         frenar_brocas()
#     except:
#         pass

#     try:
#         frenar_llantas()
#     except:
#         pass

# # PARADA NORMAL

# def parar_maquina():
#     try:
#         frenar_brocas()
#     except:
#         pass

#     try:
#         frenar_llantas()
#     except:
#         pass

# # ESPERA CON LECTURA DE ENTRADAS

# def esperar(tiempo):
#     inicio=time.time()

#     while time.time()-inicio<tiempo:

#         orden=leer_entradas()

#         if orden=='STOP':
#             return 'STOP'

#         if orden=='EMERGENCY':
#             emergencia()
#             return 'EMERGENCY'

#         if orden=='QUIT':
#             emergencia()
#             return 'QUIT'

#         time.sleep(0.02)

#     return None

# # CICLO

# def ciclo():
#     global estado,emergencia_activa

#     estado='MARCHA'
#     emergencia_activa=False

#     print("\nMAQUINA EN MARCHA")

#     while estado=='MARCHA':

#         # 1. LLANTAS 10 CM
#         print("\nLLANTAS -> 10 CM")

#         arrancar_llantas()

#         tiempo_mov=DISTANCIA_MOVIMIENTO/(VEL_RPM*CIRCUNFERENCIA/60)

#         orden=esperar(tiempo_mov)

#         frenar_llantas()

#         if orden=='STOP':
#             estado='PARADA'
#             break

#         if orden in ['EMERGENCY','QUIT']:
#             estado='PARADA'
#             break

#         # 2. ESTUN 5 SEGUNDOS
#         print("ESTUN -> 5 SEGUNDOS")

#         if not arrancar_brocas():
#             estado='PARADA'
#             break

#         orden=esperar(TIEMPO_BROCAS)

#         frenar_brocas()

#         if orden=='STOP':
#             estado='PARADA'
#             break

#         if orden in ['EMERGENCY','QUIT']:
#             estado='PARADA'
#             break

#         # 3. REPETIR
#         print("REPITIENDO CICLO")

#     parar_maquina()
#     print("\nMAQUINA DETENIDA")

# # PRINCIPAL

# def main():
#     global estado,emergencia_activa

#     print("\n=== CONTROL MAQUINA ===")
#     print("A = ARRANQUE")
#     print("B = PARO")
#     print("P = EMERGENCIA")
#     print("Q = SALIR")
#     print("GPIO 17 = ARRANQUE")
#     print("GPIO 27 = PARO")
#     print("======================")

#     try:
#         while True:

#             orden=leer_entradas()

#             if orden=='START' and estado=='PARADA':
#                 ciclo()

#             elif orden=='STOP':
#                 estado='PARADA'
#                 parar_maquina()

#             elif orden=='EMERGENCY':
#                 emergencia()
#                 estado='PARADA'

#             elif orden=='QUIT':
#                 emergencia()
#                 break

#             time.sleep(0.02)

#     except KeyboardInterrupt:
#         emergencia()

#     except Exception as e:
#         print("ERROR:",e)
#         emergencia()

#     finally:
#         try:
#             emergencia()
#         except:
#             pass

#         GPIO.cleanup()

#         if ser and ser.is_open:
#             ser.close()

# if __name__=="__main__":
#     main()





import time
import math
import serial
import RPi.GPIO as GPIO

PORT='/dev/ttyUSB0'

# ZLTECH
SLAVE_ID=1
BAUD_ZLTECH=115200

# ESTUN
SERVO_ID=2
BAUD_SERVO=9600

# GPIO
GPIO_START=17
GPIO_STOP=27
GPIO_EMERGENCY=22
GPIO_EMERGENCY_OUT=10

GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO_START,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_STOP,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_EMERGENCY,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_EMERGENCY_OUT,GPIO.OUT,initial=GPIO.LOW)

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
estado='PARADA'
emergencia_activa=False

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
    f+=f"{lrc(d):02X}".encode()+b"\r\n"

    ser.write(f)
    ser.flush()
    time.sleep(0.15)

    return bool(ser.read(50))

def int_a_4bytes(n):
    b=n.to_bytes(4,'big',signed=True)
    return b[:2],b[2:]

# LLANTAS

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

    print("LLANTAS: 10 CM")

def frenar_llantas():
    abrir_puerto(BAUD_ZLTECH)

    rtu(bytearray([
        SLAVE_ID,6,
        0x20,0x0E,
        0,7
    ]))

    print("LLANTAS: PARADAS")

# ESTUN

def arrancar_brocas():
    abrir_puerto(BAUD_SERVO,'O')

    if not ascii_write(0x1023,1):
        print("ERROR ESTUN")
        return False

    time.sleep(0.3)

    if not ascii_write(0x1024,1):
        print("ERROR JOG")
        return False

    print("ESTUN: 5 SEGUNDOS")
    return True

def frenar_brocas():
    abrir_puerto(BAUD_SERVO,'O')

    ascii_write(0x1024,0)

    time.sleep(0.3)

    ascii_write(0x1023,0)

    print("ESTUN: PARADO")

# ENTRADAS

def leer_entradas():
    global emergencia_activa

    # GPIO22 NC: HIGH = emergencia
    if GPIO.input(GPIO_EMERGENCY)==GPIO.HIGH:
        emergencia_activa=True
        return 'EMERGENCY'

    # GPIO17 = arranque
    if GPIO.input(GPIO_START)==GPIO.LOW:
        time.sleep(0.05)
        if GPIO.input(GPIO_START)==GPIO.LOW:
            return 'START'

    # GPIO27 = paro
    if GPIO.input(GPIO_STOP)==GPIO.LOW:
        time.sleep(0.05)
        if GPIO.input(GPIO_STOP)==GPIO.LOW:
            return 'STOP'

    return None

# PARADA NORMAL

def parar_maquina():
    try:
        frenar_brocas()
    except:
        pass

    try:
        frenar_llantas()
    except:
        pass

# EMERGENCIA

def emergencia():
    global emergencia_activa,estado

    emergencia_activa=True
    estado='PARADA'

    print("\n!!! PARADA DE EMERGENCIA !!!")

    try:
        frenar_brocas()
    except:
        pass

    try:
        frenar_llantas()
    except:
        pass

    # Activa salida GPIO10
    GPIO.output(GPIO_EMERGENCY_OUT,GPIO.HIGH)

    print("GPIO10: ACTIVADO")

# ESPERA

def esperar(tiempo):
    inicio=time.time()

    while time.time()-inicio<tiempo:

        orden=leer_entradas()

        if orden=='STOP':
            return 'STOP'

        if orden=='EMERGENCY':
            emergencia()
            return 'EMERGENCY'

        time.sleep(0.02)

    return None

# CICLO

def ciclo():
    global estado,emergencia_activa

    estado='MARCHA'
    emergencia_activa=False

    # Asegurar salida de emergencia apagada
    GPIO.output(GPIO_EMERGENCY_OUT,GPIO.LOW)

    print("\nMAQUINA EN MARCHA")

    while estado=='MARCHA':

        # LLANTAS 10 CM
        print("\nLLANTAS -> 10 CM")

        arrancar_llantas()

        tiempo_mov=DISTANCIA_MOVIMIENTO/(VEL_RPM*CIRCUNFERENCIA/60)

        orden=esperar(tiempo_mov)

        frenar_llantas()

        if orden=='STOP':
            estado='PARADA'
            break

        if orden=='EMERGENCY':
            break

        # ESTUN 5 SEGUNDOS
        print("ESTUN -> 5 SEGUNDOS")

        if not arrancar_brocas():
            estado='PARADA'
            break

        orden=esperar(TIEMPO_BROCAS)

        frenar_brocas()

        if orden=='STOP':
            estado='PARADA'
            break

        if orden=='EMERGENCY':
            break

        print("REPITIENDO CICLO")

    if not emergencia_activa:
        parar_maquina()

    print("\nMAQUINA DETENIDA")

# PRINCIPAL

def main():
    global estado

    print("=== CONTROL MAQUINA ===")
    print("GPIO17 = ARRANQUE")
    print("GPIO27 = PARO")
    print("GPIO22 = EMERGENCIA NC")
    print("GPIO10 = SALIDA EMERGENCIA")
    print("=======================")

    try:
        while True:

            # Emergencia física siempre tiene prioridad
            if GPIO.input(GPIO_EMERGENCY)==GPIO.HIGH:
                emergencia()
                time.sleep(0.1)
                continue

            orden=leer_entradas()

            if orden=='START' and estado=='PARADA':
                ciclo()

            elif orden=='STOP':
                estado='PARADA'
                parar_maquina()

            elif orden=='EMERGENCY':
                emergencia()

            time.sleep(0.02)

    except KeyboardInterrupt:
        emergencia()

    except Exception as e:
        print("ERROR:",e)
        emergencia()

    finally:
        try:
            emergencia()
        except:
            pass

        GPIO.cleanup()

        if ser and ser.is_open:
            ser.close()

if __name__=="__main__":
    main()
