"""Retired CLI. Request restore through the authenticated removal UI (approval + confirmation)."""
import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--sku", required=True)
    parser.parse_args()
    parser.error("Use Restaurar na interface autenticada do PRM; a CLI não autoriza operações.")


if __name__ == "__main__":
    main()
