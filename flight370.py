import socket
import time
import random
import math
import binascii
import argparse

# Location coordinates
AUGUSTA_LAT = 33.3699
AUGUSTA_LON = -81.9645

COLUMBIA_LAT = 33.961436
COLUMBIA_LON = -81.143562

ORANGE_LAT = 33.599107
ORANGE_LON = -81.030564

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

def create_velocity_message(icao_hex, speed_knots, heading, vertical_rate):
    """
    Create an airborne velocity message (Type Code 19)
    This contains the aircraft's heading which will orient the icon correctly
    
    Args:
        icao_hex: Aircraft ICAO address
        speed_knots: Ground speed in knots
        heading: Track angle in degrees (0-359)
        vertical_rate: Vertical rate in feet per minute
        
    Returns:
        Complete ADS-B velocity message
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
    
    # TC 19 (airborne velocity) subtype 1 (ground speed)
    msg[4] = 0x99  # TC=19, subtype=1
    
    # Convert heading and speed to East-West and North-South components
    heading_rad = math.radians(heading)
    east_west = speed_knots * math.sin(heading_rad)
    north_south = speed_knots * math.cos(heading_rad)
    
    # Encode East-West velocity
    ew_sign = 0 if east_west >= 0 else 1
    ew_value = min(1023, int(abs(east_west)))
    
    # Encode North-South velocity
    ns_sign = 0 if north_south >= 0 else 1
    ns_value = min(1023, int(abs(north_south)))
    
    # Encode vertical rate (in 64 feet per minute units)
    vr_sign = 0 if vertical_rate >= 0 else 1
    vr_value = min(511, int(abs(vertical_rate) / 64))
    
    # Pack into the message
    msg[5] = 0x01  # Intent change=0, IFR=1, NACv=0
    
    msg[6] = ((ew_sign << 7) | ((ew_value >> 3) & 0x7F))
    msg[7] = ((ew_value & 0x07) << 5) | ((ns_sign << 4) | ((ns_value >> 6) & 0x0F))
    msg[8] = ((ns_value & 0x3F) << 2) | ((vr_sign << 1) | (vr_value >> 8))
    msg[9] = (vr_value & 0xFF)
    
    # Reserved and source bits
    msg[10] = 0x00
    
    # Calculate and append CRC
    crc = crc24(msg)
    msg.append((crc >> 16) & 0xFF)
    msg.append((crc >> 8) & 0xFF)
    msg.append(crc & 0xFF)
    
    # Format in Beast/AVR ASCII format
    hex_msg = binascii.hexlify(msg).decode('ascii').upper()
    return f"*{hex_msg};"

def generate_aircraft(args):
    """Generate a realistic aircraft with ICAO address and fixed heading"""
    icao = f"{random.randint(0, 0xFFFFFF):06X}"
    
    # Generate a random heading (0-359 degrees)
    heading = random.randint(0, 359)
    
    # Generate a random offset from the center point
    offset_distance = random.uniform(0.1, 0.5)  # Distance in degrees
    offset_angle = random.uniform(0, 2 * math.pi)  # Random angle in radians
    
    # Calculate position offset from the center
    offset_lat = offset_distance * math.cos(offset_angle)
    offset_lon = offset_distance * math.sin(offset_angle)
    
    # Altitude based on aircraft type
    if random.random() < 0.3:  # 30% commercial
        altitude = random.choice([25000, 30000, 35000, 38000])
        speed = random.randint(400, 550)
        climb_rate = random.choice([-500, -300, 0, 300, 500])
    elif random.random() < 0.6:  # 30% private
        altitude = random.choice([3500, 7500, 10000, 15000])
        speed = random.randint(150, 350)
        climb_rate = random.choice([-300, -100, 0, 100, 300])
    else:  # 40% military/other
        altitude = random.choice([5000, 15000, 25000, 35000])
        speed = random.randint(300, 600)
        climb_rate = random.choice([-800, -400, 0, 400, 800])
    
    # Create the aircraft object
    return {
        'icao': icao,
        'alt': altitude,
        'speed': speed,
        'heading': heading,  # Fixed heading that won't change
        'climb_rate': climb_rate,
        'lat': args.lat + offset_lat,
        'lon': args.long + offset_lon,
        'last_update': time.time(),
        'odd_frame': False,
    }

def update_aircraft_position(aircraft, elapsed):
    """
    Update aircraft position based on heading - ensuring straight line movement
    """
    # Convert speed from knots to degrees per second
    # 1 knot ≈ 0.0003 nautical miles per second
    # 1 nautical mile ≈ 0.0166 degrees of latitude at equator
    # This gives approximately 0.000008 degrees per second per knot
    speed_deg_per_sec = aircraft['speed'] * 0.000008 * elapsed
    
    # Convert heading to radians (0° = North, 90° = East)
    heading_rad = math.radians(90 - aircraft['heading'])  # Adjust for 0° = East in math functions
    
    # Calculate position change
    # For correct straight line movement, we need to:
    # - Move northward by speed * cos(heading)
    # - Move eastward by speed * sin(heading)
    lat_change = speed_deg_per_sec * math.cos(heading_rad)
    
    # Longitude change depends on latitude (circles of longitude get smaller near poles)
    # cos(latitude) compensates for this
    lon_change = speed_deg_per_sec * math.sin(heading_rad) / math.cos(math.radians(aircraft['lat']))
    
    # Update position
    aircraft['lat'] += lat_change
    aircraft['lon'] += lon_change
    
    # Update altitude based on climb rate
    aircraft['alt'] += (aircraft['climb_rate'] / 60.0) * elapsed
    
    # Ensure altitude stays within reasonable bounds
    aircraft['alt'] = max(1000, min(45000, aircraft['alt']))
    
    # Toggle odd/even frame for CPR encoding
    aircraft['odd_frame'] = not aircraft['odd_frame']
    
    return aircraft

def send_position_reports(aircraft_list, host='localhost', port=30001):
    """Send position reports for aircraft to dump1090"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        print(f"Connected to dump1090 AVR input at {host}:{port}")
        
        while True:
            current_time = time.time()
            
            for aircraft in aircraft_list:
                # Calculate time elapsed since last update
                elapsed = current_time - aircraft['last_update']
                
                # Update aircraft position
                update_aircraft_position(aircraft, elapsed)
                aircraft['last_update'] = current_time
                
                # Generate position messages (both even and odd frames)
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
                
                # Generate velocity message (contains heading)
                velocity_message = create_velocity_message(
                    aircraft['icao'],
                    aircraft['speed'],
                    aircraft['heading'],
                    aircraft['climb_rate']
                )
                
                try:
                    # Send even frame
                    sock.sendall((even_message + "\n").encode('ascii'))
                    print(f"Sent EVEN frame for {aircraft['icao']} at {aircraft['lat']:.4f}, {aircraft['lon']:.4f}, Alt: {int(aircraft['alt'])}ft, Hdg: {int(aircraft['heading'])}°")
                    
                    # Brief pause
                    time.sleep(0.1)
                    
                    # Send odd frame
                    sock.sendall((odd_message + "\n").encode('ascii'))
                    print(f"Sent ODD frame for {aircraft['icao']}")
                    
                    # Brief pause
                    time.sleep(0.1)
                    
                    # Send velocity message (critical for icon orientation)
                    sock.sendall((velocity_message + "\n").encode('ascii'))
                    print(f"Sent VELOCITY frame for {aircraft['icao']} - Speed: {aircraft['speed']} kts, Hdg: {int(aircraft['heading'])}°")
                    
                except Exception as e:
                    print(f"Error sending messages: {e}")
                
                # Wait before processing next aircraft
                time.sleep(0.2)
            
            # Check for aircraft that have gone too far and replace them
            for i, aircraft in enumerate(aircraft_list):
                # Check if aircraft has moved too far from center
                distance = math.sqrt((aircraft['lat'] - args.lat)**2 + (aircraft['lon'] - args.long)**2)
                
                if distance > 1.0:  # If aircraft is more than ~60 miles from center
                    # Replace with a new aircraft
                    aircraft_list[i] = generate_aircraft(args)
                    print(f"Aircraft {aircraft['icao']} replaced (too far from center)")
            
            # Add/remove aircraft occasionally
            if random.random() < 0.03:  # 3% chance each cycle
                if len(aircraft_list) < args.aircraft and random.random() < 0.7:
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
        import traceback
        traceback.print_exc()
    finally:
        sock.close()
        print("Connection closed")

def main():
    parser = argparse.ArgumentParser(description='ADS-B Traffic Generator with Straight-Line Movement')
    parser.add_argument('--host', default='localhost', help='dump1090 host')
    parser.add_argument('--port', type=int, default=30001, help='dump1090 AVR input port (default: 30001)')
    parser.add_argument('--aircraft', type=int, default=10, help='Number of aircraft to simulate')
    parser.add_argument('--lat', type=float, default=AUGUSTA_LAT, help="Center latitude")
    parser.add_argument('--long', type=float, default=AUGUSTA_LON, help="Center longitude")
    
    global args
    args = parser.parse_args()

    print(f"Creating {args.aircraft} aircraft around (LAT: {args.lat}, LON: {args.long})")
    print(f"Aircraft will move in straight lines according to their heading")
    print(f"Sending data to dump1090 AVR input at {args.host}:{args.port}")
    print("Press Ctrl+C to stop the simulation")
    
    # Generate initial aircraft
    aircraft_list = [generate_aircraft(args) for _ in range(args.aircraft)]
    
    # Start sending data
    send_position_reports(aircraft_list, args.host, args.port)

if __name__ == "__main__":
    main()