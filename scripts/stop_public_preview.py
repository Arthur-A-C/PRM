"""Request graceful shutdown of the temporary public preview."""

from scripts.public_preview import STATUS, STOP


def main() -> None:
    if not STATUS.is_file():
        print("Nenhuma prévia pública ativa registrada.")
        return
    STOP.write_text("stop\n", encoding="utf-8")
    print("Solicitação de encerramento enviada; o supervisor fecha o túnel e o servidor.")


if __name__ == "__main__":
    main()
