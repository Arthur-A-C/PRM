"""Explicit download of model weights; never executed automatically by a web request."""
import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='small', choices=['small','base'])
    parser.add_argument('--cache', default='data/meetings/models')
    args=parser.parse_args()
    from faster_whisper.utils import download_model
    print(download_model(args.model,cache_dir=args.cache))


if __name__=='__main__':main()
