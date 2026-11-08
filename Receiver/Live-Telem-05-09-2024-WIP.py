##### Made with Love and finished 07/09/2024 @ 20:09 by Ethan Glen :)

##### IMPORTS ALL GUBBINS

import pandas
import numpy
import struct
import serial.tools.list_ports
from datetime import datetime
import os
import signal
from influxdb import InfluxDBClient
import math

##### SHOWS THE CURRENT PORTS

ports = serial.tools.list_ports.comports()
for port, desc, hwid in sorted(ports):
        print("{}: {}".format(port, desc))

##### THIS ASKS NAMES OF FILES YOU WANT TO CREATE

Port = str(input("What Port are you using: "))
NameOfBIN = str(input("BIN FILE NAME: "))
NameOfCSV = str(input("CSV FILE NAME: "))

NameOfBIN = str(NameOfBIN + ".BIN")
NameOfBINFilePath = os.path.join("BIN", NameOfBIN)

NameOfCSV = str(NameOfCSV + ".csv")
NameOfCSVFilePath = os.path.join("CSV", NameOfCSV)

file = open(NameOfCSVFilePath, 'w')
file1 = open(NameOfBINFilePath, 'wb')

##### NOW OPENS SERIAL PORT TO THE CORRET BAUD RATE OF 115200

SERIALPORT = Port
BAUD = 115200
serialConnection = serial.Serial(SERIALPORT, BAUD)

##### THIS GETS THE CURRENT CONFIG AND SETS THE CURRENT BYTES ARRAY TO BE NULL

DecodeConfig = pandas.read_csv("CAN-decode-sheet.csv")
BYTECANMessage = bytearray()

##### GETS THE CURRENT END OF FRAME MARKER

EndOfFrameMarker = b"\x7E"

##### SETS UP THE GPS LAT AND LON

GrafanaLonData = tuple("0.0")
GrafanaLatData = tuple("0.0")

##### EXTRACTS THE CONFIG TO A MORE SUITABLE FORM

ListOfItem = DecodeConfig["Item"]
ListOfSource = DecodeConfig["Source"]
ListOfCANID_Decimal = DecodeConfig["CAN_ID (dec)"]
ListOfDLC = DecodeConfig["DLC"]
ListOfBYTE_0 = DecodeConfig["BYTE_0"]
ListOfBYTE_1 = DecodeConfig["BYTE_1"]
ListOfBYTE_2 = DecodeConfig["BYTE_2"]
ListOfBYTE_3 = DecodeConfig["BYTE_3"]
ListOfBYTE_4 = DecodeConfig["BYTE_4"]
ListOfBYTE_5 = DecodeConfig["BYTE_5"]
ListOfBYTE_6 = DecodeConfig["BYTE_6"]
ListOfBYTE_7 = DecodeConfig["BYTE_7"]
DATATYPE1 = DecodeConfig["1"]
DATATYPE2 = DecodeConfig["2"]
DATATYPE3 = DecodeConfig["3"]
DATATYPE4 = DecodeConfig["4"]
DATATYPE5 = DecodeConfig["5"]
DATATYPE6 = DecodeConfig["6"]
DATATYPE7 = DecodeConfig["7"]
DATATYPE8 = DecodeConfig["8"]

print(" -> LOADED DATA")

##########################

##### SET UP INFLUX DB

user = "admin"
password = "password"
DataBaseName = "DUSCiESC"
Port = "8086"
Host = "localhost"

client = InfluxDBClient(Host, Port, user, password, DataBaseName)

print(" -> SET UP INFLUXDB ")
print(" -> GRAFANA READY ")

##########################

def signal_handler(sig, frame):
    print("\n Live Telemetry Ended ")
    print(" |")
    print(" -> Files Saved")
    print(" -> Closed Influxdb")
    file1.close()
    file.close()
    exit(0)

##### FUNCTION THAT THIS FIND THE INDEX (ROW) FOR THE CAN MESSGAE IN THE CONFIG
def Get_Iteration(FoundCANID):

    Number_Of_CANIDs = len(ListOfCANID_Decimal)
    for CANID in range(Number_Of_CANIDs):
        if FoundCANID == ListOfCANID_Decimal[CANID]:
            Index = CANID
            break

        elif CANID == Number_Of_CANIDs-1:
            print(("Failed Message CANID Unknown, CANID: %d") % (FoundCANID))
            # Can be whatever number just > than the list of can number lmaooo
            Index = 99

    return Index

##### FUNCTION THAT RETURN THE NUMBER OF BYTES THERE SHOULD BE AND HOW TO DECODE IT WITH STRUCT
def Turn_String_Into_Letter(String):

    if String == "int8":
        return "b", 1
    elif String == "uint8":
        return "B", 1
    elif String == "int16":
        return "h", 2
    elif String == "uint16":
        return "H", 2
    elif String == "int32":
        return "i", 4
    elif String == "uint32":
        return "I", 4
    elif String == "char":
        return "c", 1
    elif String == "float":
        return "f", 4
    elif String == "spare1":
        return "b", 1
    elif String == "spare2":
        return "b", 1
    elif String == "spare3":
        return "b", 1


##########################
##########################


##### MAIN LOOP
while True:

    ##### THIS AWAITS A CONNECTION TO THE TRANSMITTER XBEE

    if serialConnection.in_waiting:
        inputByte = serialConnection.read(size=1)  # Read byte
        file1.write((inputByte))

        if inputByte == EndOfFrameMarker:
            print("Decoding: " + str(BYTECANMessage))

            ##### TD01 TD02 TD03 TD04 CANID0 CANID1 DLC B1 B2 B3 B4 B5 B6 B7 B8 CR01 CR02

            ## 8 IS KINDA A ARBITARY VALUE AS A MESSAGE < 8 IS NULL

            if len(BYTECANMessage) > 8:
                # Remove the 2 ending Values & four starting bytes
                Length_Of_CAN_Message = len(BYTECANMessage) - 2
                Byte_Data_With_CANID = BYTECANMessage[4:Length_Of_CAN_Message]
                Byte_Time_Data = BYTECANMessage[0:4]

                ##### UNPACKS THE MILLIES FROM THE ARDUNIO BUT IS CURRENTLY NOT USED
                CurrentMillisFromArudnio = struct.unpack("<I", Byte_Time_Data)

                ##### DATA BYTEARRAY

                Byte_Data = BYTECANMessage[7:Length_Of_CAN_Message]
                
                ##### CANID AND DLC, CANID IS A UINT16 DLC UINT8
                
                CANID_AND_DLC = struct.unpack(">HB", Byte_Data_With_CANID[0:3])
                
                ##### THIS GETS THE CORRECT LINE IN THE CONFIG THAT THE MESSAGE RELATES TO

                Index = Get_Iteration(CANID_AND_DLC[0])
                
                # THIS STOPS THE REST DYING LMAO
                if Index == 99:
                    BYTECANMessage = bytearray()
                    print((" -> CAN ID: %s Not Found In Decode Sheet") %(str(CANID_AND_DLC[0]))) 
                    continue

                # SANITY CHECK
                DLC_From_SpreadSheet = ListOfDLC[Index]
                if CANID_AND_DLC[1] != DLC_From_SpreadSheet:
                    print("Error in DLC")
                    BYTECANMessage = bytearray()
                    continue

                ##### THIS IS A ARRAY OF WHAT THE BYTES MEAN IN THE MESSAGE

                Byte_Meaning_Array = numpy.array(
                    [ListOfBYTE_0[Index], ListOfBYTE_1[Index], ListOfBYTE_2[Index], ListOfBYTE_3[Index],
                     ListOfBYTE_4[Index],
                     ListOfBYTE_5[Index], ListOfBYTE_6[Index], ListOfBYTE_7[Index]])

                ##### THEN THIS IS HOW TO DECODE EACH OF THE VALUES IN THE MESSAGE

                Byte_Decode_Array = numpy.array([DATATYPE1[Index], DATATYPE2[Index], DATATYPE3[Index], DATATYPE4[Index]
                                                    , DATATYPE5[Index], DATATYPE6[Index], DATATYPE7[Index],
                                                 DATATYPE8[Index]])

                ##### NOW I GOTTA REMOVE THE CRAP IN THE CONFIG SUCH THAT ITS USEABLE :)

                InUse = numpy.where(Byte_Meaning_Array == "IN USE")
                Dash = numpy.where(Byte_Meaning_Array == "-")
                Dash2 = numpy.where(Byte_Decode_Array == "-")
                spare1 = numpy.where(Byte_Meaning_Array == "spare1")
                spare2 = numpy.where(Byte_Meaning_Array == "spare2")
                spare3 = numpy.where(Byte_Meaning_Array == "spare3")

                ##### THIS NOW JUST LEAVES THE BYTES

                Index_To_Be_Removed_To_Make_Name_Array = numpy.concatenate((InUse, Dash, spare1, spare2, spare3),
                                                                           axis=None)
                Byte_Name_Array = numpy.delete(Byte_Meaning_Array, Index_To_Be_Removed_To_Make_Name_Array, axis=None)

                ##### SAME AS ABOVE BUT WITH THE DECODE ARRAY

                Byte_Decode_Array = numpy.delete(Byte_Decode_Array, Dash2, axis=None)

                ##### THIS FILLS UP THE STRUCT MESSAGE SUCH THAT IT UNPACKS IT CORRECTLY BY USEING THE FUNCTION TURN_STRING_INTO_LETTER

                Letters_For_Struct = ""
                Number_Of_Bytes = 0
                for Data in range(len(Byte_Decode_Array)):
                    Decode_Method = Byte_Decode_Array[Data]
                    Letter_Number_tuple = Turn_String_Into_Letter(Decode_Method)
                    Letter = Letter_Number_tuple[0]
                    Number = Letter_Number_tuple[1]
                    Letters_For_Struct = Letters_For_Struct + Letter
                    Number_Of_Bytes = Number_Of_Bytes + Number

                ##### NOW GETS THE RAW DATA AND UNPACKS IT WHOOOP WHOOOP

                Raw_Byte_Data = Byte_Data[:Number_Of_Bytes]
                print("Decoding: " + str(Raw_Byte_Data))
                print(("CAN ID: %d DLC: %d Source: %s Item: %s") % (CANID_AND_DLC[0], CANID_AND_DLC[1], ListOfSource[Index], ListOfItem[Index]))

                ##### THIS IS TO CHECK THAT THE BYTES RECIVED IS WHAT WE EXPECTED AKA THE DLC

                if len(Raw_Byte_Data) < CANID_AND_DLC[1]:
                    print("Message Failed: length too short")
                    BYTECANMessage = bytearray()
                    continue

                ##### THE ORION SENDS MESSAGES IN BIG ENDIAN FORMAT SO MUST UNPACK THE SAME WAY :)

                if ListOfSource[Index] == "Orion":
                    
                    ##### BIG ENDIAN
                    
                    Message_for_unpack = ">" + Letters_For_Struct
                else:
                    Message_for_unpack = "<" + Letters_For_Struct
                    
                ##### THIS IS CHECK THAT THEIR IS ACTUALLY DATA TO BE REVIEWED AND SEND TO THE DATA BASE

                if len(Raw_Byte_Data) == 0:
                    print("No Data")
                    BYTECANMessage = bytearray()
                    continue
                else:
                    Data = struct.unpack(Message_for_unpack, Raw_Byte_Data)

                ##### GPS LAT AND LONG COME IN A WEIRD STRING AND THIS SETS IT CORRECTLY
                
                ### START OF IF

                if CANID_AND_DLC[0] == 248:
                    Lat_Long_Data = Data[0]

                    ##### THE MAGIC SENTANCE

                    Real_Lat_Long_Data = Lat_Long_Data // 100 + (Lat_Long_Data % 100) / 60

                    ##### A BIT SILLY BUT AS I USE TUPLES I AND YOU CANNOT CHANGE VALUES IN TUPLES MAKE A LIST THEN CHANGE THEN CHANGE BACK TO A TUPLE 

                    Data = list(Data)
                    Data[0] = Real_Lat_Long_Data
                    Data = tuple(Data)
                    
                    ##### THIS IS FOR GRAFANA SO WE CAN SEE THE LOCATION IN GEOMAPS !!

                    GrafanaLatData = list("")
                    if Data[1] == b'N':
                        GrafanaLatData.append(Real_Lat_Long_Data)
                    elif Data[1] == b'S':
                        GrafanaLatData.append(-1 * Real_Lat_Long_Data)
                    else:
                        GrafanaLatData.append(0)
                        print("Error in Lat Neither North or South")
                        BYTECANMessage = bytearray()
                        continue

                    GrafanaLatData = tuple(GrafanaLatData)
                

                ##### THIS IS THE SAME AS BEFORE

                elif CANID_AND_DLC[0] == 249:
                    Lat_Long_Data = Data[0]
                    Real_Lat_Long_Data = Lat_Long_Data // 100 + (Lat_Long_Data % 100) / 60
                    
                    ##### SILLY TUPLE THINGY

                    Data = list(Data)
                    Data[0] = Real_Lat_Long_Data
                    Data = tuple(Data)

                    
                    ##### THIS IS USED FOR GRAFANA

                    GrafanaLonData = list("")
                    if Data[1] == b'E':
                        GrafanaLonData.append(Real_Lat_Long_Data)
                    elif Data[1] == b'W':
                        GrafanaLonData.append(-1 * Real_Lat_Long_Data)
                    else:
                        GrafanaLonData.append(0)
                        print("Error in Lon Neither East or West")
                        BYTECANMessage = bytearray()
                        continue

                    GrafanaLonData = tuple(GrafanaLonData)

                else:
                    Data = Data
                ### END OF GPS IF

                ###### THIS IS THE ACTUAL OUTPUT AND WHERE STUFF ACTUALLY HAPPENS

                CurrentTime = datetime.utcnow()
                file.write(str(CurrentTime))
                file.write(",")
                

                ###### THIS IS JUST TO MAKE THE CODE RUN WITHOUT STOPPING AS SOMETIMES VALUES ARE NAN

                for Peice_Of_Data in range(len(Byte_Name_Array)): 
                    if isinstance(Data[Peice_Of_Data], bytes) == False:
                            if math.isnan(Data[Peice_Of_Data]) == True:
                                BYTECANMessage = bytearray()
                                print("Data is NaN")
                                continue
                    
                    ##### THIS WRITES THE VALUES AND WHAT THEY MEAN TO THE TERMINAL

                    print((" -> %s: %s: %s") % (str(CurrentTime), str(Byte_Name_Array[Peice_Of_Data]), str(Data[Peice_Of_Data])))
                    file.write(str(Byte_Name_Array[Peice_Of_Data]))
                    file.write(",")
                    file.write(str(Data[Peice_Of_Data]))
                    file.write(",")

                    ##### SEND TO A DATABASE

                    if CANID_AND_DLC[0] != 248 and CANID_AND_DLC[0] != 249 and CANID_AND_DLC[0] != 1809 and CANID_AND_DLC[0] != 1810:

                        JSON_Data = [
                            {
                                "measurement": str(Byte_Name_Array[Peice_Of_Data]),
                                "time": str(CurrentTime),
                                "fields": {
                                "Float_value": Data[Peice_Of_Data],
                                "Bool_value" : True
                            }
                        }
                        ]
                        
                        client.write_points(JSON_Data)
                    
                    ##### HAD TO DO A MAKE A EXTRA SEND CLAUSE AS THE GPS HAS TO BE IN THE CORRECT FORMAT -/+

                    elif CANID_AND_DLC[0] == 248 or CANID_AND_DLC[0] == 249:
                        
                        print((" -> Sending Latitude AND Longitude %s %s") % (str(GrafanaLatData[0]), str(GrafanaLonData[0])))
                        
                        ##### THIS IS THE WAY TO FORMAT THE DATA TO BE SENT TO THE INFLUX DATABASE SPELLING IS IMPORTANT!!
                        
                        JSON_Data = [
                                {
                                    "measurement": "location",
                                    "time": str(CurrentTime),
                                    "fields": {
                                    "latitude": float((GrafanaLatData[0])),
                                    "longitude": float((GrafanaLonData[0])),
                                    "Bool_value": True
                                }
                        }
                        ]
                        
                        ##### THIS WRITES THE JSON DATA TO THE INFLUX DATA BASE

                        client.write_points(JSON_Data)
                        
                        
                file.write("\n")

                ##### RESETS THE BYTEARRAY

                BYTECANMessage = bytearray()

            else:
                print("Failed Message: Length Not Long enough")
        else:

            ##### NICE LITTLER HANDLER SO THAT THE FILES ARE SAVED NO MATTER WHAT

            BYTECANMessage.extend(inputByte)
            signal.signal(signal.SIGINT, signal_handler)
