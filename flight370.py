import socket

import time

import random

import math

import binascii

import argparse



# Augusta Regional Airport coordinates
#unused 

AUGUSTA_LAT = 33.3699

AUGUSTA_LON = -81.9645


COLUMBIA_LAT = 33.961436
COLUMBIA_LON = -81.143562

ORANGE_LAT = 33.599107
ORANGE_LONG = -81.030564




# CPR constants from dump1090.c

NZ = 15  # Number of geographic latitude zones



def crc24(msg):

    """

    Calculate CRC-24 for ADS-B messages using the polynomial from dump1090.c

    """

    GENERATOR = 0x1FFF409

    crc = 0

    

    for byte in msg:

        crc ^= (byte << 16)

        for _ in range(8):

            crc <<= 1

            if crc & 0x1000000:

                crc ^= GENERATOR

    

    return crc & 0xFFFFFF



def floor(x):

    """Integer floor function"""

    return int(math.floor(x))



def cprNL(lat):

    """

    NL function from dump1090.c - Calculate the number of longitude zones

    """

    if lat == 0:

        return 59

    if lat == 87 or lat == -87:

        return 2

    if lat > 87 or lat < -87:

        return 1

    

    # Compute using the same formula as in dump1090.c

    tmp = 1.0 - math.cos(math.pi / (2.0 * NZ))

    tmp = tmp / math.pow(math.cos(math.pi * lat / 180.0), 2)

    tmp = math.acos(1.0 - tmp)

    

    return floor(2.0 * math.pi / tmp)



def cprDlat(cprEncType):

    """Return the size of a latitude zone"""

    return 360.0 / (4 * NZ - cprEncType)



def cprDlon(lat, cprEncType):

    """Return the size of a longitude zone at the given latitude"""

    nl = cprNL(lat)

    if nl == 0:

        return 0

    return 360.0 / max(1, nl - cprEncType)



def encode_cpr_position(lat, lon, is_odd):

    """

    Encode CPR position exactly as expected by dump1090.c

    

    Args:

        lat: Latitude in degrees

        lon: Longitude in degrees

        is_odd: True for odd CPR format, False for even

    

    Returns:

        (lat_cpr, lon_cpr) as 17-bit integers

    """

    # Limit latitude to valid range

    lat = max(-90, min(90, lat))

    

    # Normalize longitude to -180..+180

    while lon < -180:

        lon += 360

    while lon >= 180:

        lon -= 360

    

    # CPR encode type (0 for even, 1 for odd)

    cprEncType = 1 if is_odd else 0

    

    # Calculate zone sizes

    dlat = cprDlat(cprEncType)

    dlon = cprDlon(lat, cprEncType)

    

    # Compute latitude index (YZ)

    # Exactly matching dump1090's method

    lat_cpr = floor(2**17 * ((lat % dlat) / dlat))

    

    # Compute longitude index (XZ)

    lon_cpr = floor(2**17 * ((lon % dlon) / dlon))

    

    # Ensure 17-bit values

    lat_cpr &= 0x1FFFF

    lon_cpr &= 0x1FFFF

    

    return lat_cpr, lon_cpr



def encode_altitude(altitude_ft):

    """

    Encode altitude following dump1090.c's decoding logic

    """

    # Round to nearest 25ft increment

    altitude_ft = round(altitude_ft / 25.0) * 25

    

    # Calculate N value (Gillham code with Q=1)

    n = int(altitude_ft / 25)

    

    # Set Q bit (1 for 25ft resolution)

    q_bit = 1

    

    # Construct 12-bit altitude field

    altitude_encoded = (n & 0x7FF) | (q_bit << 11)

    

    return altitude_encoded



def create_airborne_position_message(icao_hex, lat, lon, altitude, is_odd):

    """

    Generate a complete ADS-B message following dump1090.c's formats

    """

    # Convert ICAO to integer

    if isinstance(icao_hex, str):

        icao_int = int(icao_hex, 16)

    else:

        icao_int = icao_hex

    

    # Create message buffer (11 bytes before CRC)

    msg = bytearray(11)

    

    # DF 17 (ADS-B message) with CA=5

    msg[0] = 0x8D

    

    # ICAO address (24 bits)

    msg[1] = (icao_int >> 16) & 0xFF

    msg[2] = (icao_int >> 8) & 0xFF

    msg[3] = icao_int & 0xFF

    

    # TC 11 (airborne position) with surveillance status 0

    msg[4] = 0x58

    

    # Encode altitude

    alt_encoded = encode_altitude(altitude)

    

    # Encode position

    lat_cpr, lon_cpr = encode_cpr_position(lat, lon, is_odd)

    

    # F flag (0 for even, 1 for odd)

    f_flag = 1 if is_odd else 0

    

    # Pack the data

    # Format is:

    # - Byte 5: High 8 bits of altitude

    # - Byte 6: Low 4 bits of altitude + T flag (0) + F flag + 2 high bits of lat

    # - Byte 7: Next 8 bits of lat

    # - Byte 8: Low 7 bits of lat + highest bit of lon

    # - Byte 9: Next 8 bits of lon

    # - Byte 10: Low 8 bits of lon

    

    msg[5] = (alt_encoded >> 4) & 0xFF

    msg[6] = ((alt_encoded & 0x0F) << 4) | (0 << 3) | (f_flag << 2) | ((lat_cpr >> 15) & 0x03)

    msg[7] = (lat_cpr >> 7) & 0xFF

    msg[8] = ((lat_cpr & 0x7F) << 1) | ((lon_cpr >> 16) & 0x01)

    msg[9] = (lon_cpr >> 8) & 0xFF

    msg[10] = lon_cpr & 0xFF

    

    # Calculate and append CRC

    crc = crc24(msg)

    msg.append((crc >> 16) & 0xFF)

    msg.append((crc >> 8) & 0xFF)

    msg.append(crc & 0xFF)

    

    # Format in Beast/AVR ASCII format

    hex_msg = binascii.hexlify(msg).decode('ascii').upper()

    return f"*{hex_msg};"



def generate_aircraft(args):

    """Generate a realistic aircraft with ICAO address"""

    icao = f"{random.randint(0, 0xFFFFFF):06X}"

    

    # Generate a random offset from Augusta airport (within ~25 miles)

    offset_lat = random.uniform(-0.3, 0.3)

    offset_lon = random.uniform(-0.3, 0.3)

    

    return {

        'icao': icao,

        'alt': random.choice([3500, 7500, 10000, 15000, 20750, 25000, 32000, 35000]),

        'speed': random.randint(250, 500),

        'heading': random.randint(0, 359),

        'climb_rate': random.choice([-500, -300, -100, 0, 0, 0, 100, 300, 500]),

        'lat': args.lat + offset_lat,

        'lon': args.long + offset_lon,

        'last_update': time.time()

    }



def update_aircraft_position(aircraft):

    """Update aircraft position based on speed and heading"""

    now = time.time()

    elapsed = now - aircraft['last_update']

    aircraft['last_update'] = now

    

    # Convert speed from knots to degrees per second (approximate)

    speed_deg_per_sec = aircraft['speed'] * 0.000008 * elapsed

    

    # Update position based on heading

    heading_rad = math.radians(aircraft['heading'])

    aircraft['lat'] += math.cos(heading_rad) * speed_deg_per_sec

    aircraft['lon'] += math.sin(heading_rad) * speed_deg_per_sec / math.cos(math.radians(aircraft['lat']))

    

    # Update altitude based on climb rate

    aircraft['alt'] += (aircraft['climb_rate'] / 60.0) * elapsed

    

    return aircraft



def send_position_reports(aircraft_list, host='localhost', port=30001):

    """Send position reports for aircraft to dump1090"""

    try:

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        sock.connect((host, port))

        print(f"Connected to dump1090 AVR input at {host}:{port}")

        

        while True:

            for aircraft in aircraft_list:

                # Update aircraft position

                update_aircraft_position(aircraft)

                

                # Generate both even and odd frames

                even_message = create_airborne_position_message(

                    aircraft['icao'],

                    aircraft['lat'],

                    aircraft['lon'],

                    aircraft['alt'],

                    False  # even frame

                )

                

                odd_message = create_airborne_position_message(

                    aircraft['icao'],

                    aircraft['lat'],

                    aircraft['lon'],

                    aircraft['alt'],

                    True  # odd frame

                )

                

                try:

                    # Send even frame

                    sock.sendall((even_message + "\n").encode('ascii'))

                    print(f"Sent EVEN frame for {aircraft['icao']} at {aircraft['lat']:.4f}, {aircraft['lon']:.4f}, {int(aircraft['alt'])}ft")

                    

                    # Brief pause to let dump1090 process

                    time.sleep(0.1)

                    

                    # Send odd frame

                    sock.sendall((odd_message + "\n").encode('ascii'))

                    print(f"Sent ODD frame for {aircraft['icao']} at {aircraft['lat']:.4f}, {aircraft['lon']:.4f}, {int(aircraft['alt'])}ft")

                    

                except Exception as e:

                    print(f"Error sending messages: {e}")

                

                # Wait a bit before processing next aircraft

                time.sleep(0.2)

            

            # Add/remove aircraft occasionally

            if random.random() < 0.05:  # 5% chance each cycle

                if len(aircraft_list) < 15 and random.random() < 0.7:

                    new_aircraft = generate_aircraft(args)

                    aircraft_list.append(new_aircraft)

                    print(f"New aircraft added: {new_aircraft['icao']}")

                elif len(aircraft_list) > 5:

                    removed = aircraft_list.pop(random.randint(0, len(aircraft_list)-1))

                    print(f"Aircraft removed: {removed['icao']}")

            

            # Pause between complete update cycles

            time.sleep(1)

            

    except KeyboardInterrupt:

        print("\nSimulation stopped by user")

    except Exception as e:

        print(f"Error occurred: {e}")

    finally:

        sock.close()

        print("Connection closed")



def main():

    parser = argparse.ArgumentParser(description='ADS-B Traffic Generator for Augusta, GA')

    parser.add_argument('--host', default='localhost', help='dump1090 host')

    parser.add_argument('--port', type=int, default=30001, help='dump1090 AVR input port (default: 30001)')

    parser.add_argument('--aircraft', type=int, default=10, help='Number of aircraft to simulate')

    parser.add_argument('--lat', type=float, help="Latitude")
    
    parser.add_argument('--long', type=float, help="Longitude")

    args = parser.parse_args()



    print(f"Creating {args.aircraft} aircraft over Augusta, GA (LAT: {args.lat}, LON: {args.long})")

    print(f"Sending data to dump1090 AVR input at {args.host}:{args.port}")

    print("Press Ctrl+C to stop the simulation")

    # Generate initial aircraft
    aircraft_list = [generate_aircraft(args) for _ in range(args.aircraft)]
    # Start sending data
    send_position_reports(aircraft_list, args.host, args.port)

if __name__ == "__main__":

    main()
