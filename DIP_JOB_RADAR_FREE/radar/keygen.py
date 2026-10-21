"""Create a strong Fernet key; copy into RADAR_STATE_KEY GitHub Actions secret."""
from radar.private_state import generate_key

if __name__ == "__main__":
    print(generate_key())
