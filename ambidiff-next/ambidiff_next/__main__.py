"""Inicia somente em loopback; porta distinta do AmbiDiff legado."""
import argparse
from .web import create_app


def main():
    parser=argparse.ArgumentParser(description='AmbiDiff Next local')
    parser.add_argument('--port',type=int,default=5011)
    parser.add_argument('--data-dir',default=None)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Porta deve estar entre 1024 e 65535.')
    create_app(args.data_dir).run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)


if __name__=='__main__':main()
