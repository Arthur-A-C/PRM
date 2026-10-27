"""Retired CLI: restore file associations through the authenticated Cadastro via API UI."""
import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--sku", required=True)
    parser.parse_args()
    parser.error("Use Restaurar selecionados na interface autenticada, com confirmação da operação.")


if __name__ == "__main__":
    main()
