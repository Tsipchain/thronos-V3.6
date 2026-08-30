"""
Maker Agent CLI — command-line interface for the printer operator.

Run from the friend's machine (where printer + miner are connected):

    # Using config file:
    python -m maker_agent --config maker_config.json batch \\
        --product coin-v1 --sku TPC-S1 --design benchy.3mf \\
        --gcode benchy.gcode --quantity 5 --fee 25

    # Using inline args:
    python -m maker_agent \\
        --node http://192.168.1.10:5000 \\
        --key-file wallet.key \\
        --tenant aisthetic \\
        --printer BAMBU-X1C-001 \\
        batch --product coin-v1 --sku TPC-S1 --design benchy.3mf \\
              --gcode benchy.gcode --quantity 5

Config file format (maker_config.json):
    {
        "node_url": "http://192.168.1.10:5000",
        "key_file": "wallet.key",
        "tenant_id": "aisthetic",
        "printer_id": "BAMBU-X1C-001"
    }
"""

import argparse
import json
import logging
import sys

from .agent import MakerAgent


def _get_agent(args) -> MakerAgent:
    if args.config:
        return MakerAgent.from_config(args.config)

    key_hex = args.key
    if not key_hex and args.key_file:
        with open(args.key_file, 'r') as f:
            key_hex = f.read().strip()
    if not key_hex:
        print("Error: provide --key, --key-file, or --config")
        sys.exit(1)
    if not args.node:
        print("Error: provide --node or --config")
        sys.exit(1)

    return MakerAgent(
        node_url=args.node,
        private_key_hex=key_hex,
        tenant_id=args.tenant or 'default',
        printer_id=args.printer or '',
    )


def cmd_info(agent, args):
    print(f"Address:   {agent.address}")
    print(f"Public key: {agent.signer.public_key_hex}")
    print(f"Node:      {agent.node_url}")
    print(f"Tenant:    {agent.tenant_id}")
    print(f"Printer:   {agent.printer_id or '(not set)'}")


def cmd_approve(agent, args):
    result = agent.approve_self()
    print(json.dumps(result, indent=2))


def cmd_batch(agent, args):
    if not args.design:
        print("Error: --design required")
        sys.exit(1)
    if not args.sku:
        print("Error: --sku required")
        sys.exit(1)

    result = agent.create_batch(
        product_id=args.product,
        sku=args.sku,
        design_file=args.design,
        quantity=args.quantity,
        edition_start=args.edition_start,
        edition_size=args.edition_size,
        creation_fee=args.fee,
        batch_id=args.batch_id,
    )
    print(json.dumps(result, indent=2, default=str))

    if result.get('ok') and args.gcode:
        jobs = result.get('jobs', [])
        print(f"\nUploading gcode for {len(jobs)} jobs...")
        for job in jobs:
            gc = agent.upload_gcode(job['job_id'], args.gcode)
            status = 'OK' if gc.get('ok') else gc.get('error', 'failed')
            print(f"  {job['job_id']}: {status}")


def cmd_gcode(agent, args):
    result = agent.upload_gcode(args.job_id, args.file)
    print(json.dumps(result, indent=2, default=str))


def cmd_start(agent, args):
    result = agent.start_print(args.job_id, args.printer)
    print(json.dumps(result, indent=2, default=str))


def cmd_complete(agent, args):
    result = agent.complete_print(args.job_id)
    print(json.dumps(result, indent=2, default=str))


def cmd_fail(agent, args):
    result = agent.fail_print(args.job_id, args.reason or '')
    print(json.dumps(result, indent=2, default=str))


def cmd_certify(agent, args):
    result = agent.certify(args.job_id)
    print(json.dumps(result, indent=2, default=str))


def cmd_status(agent, args):
    result = agent.get_job_status(args.job_id)
    print(json.dumps(result, indent=2, default=str))


def cmd_jobs(agent, args):
    result = agent.list_jobs(batch_id=args.batch_id, status=args.status)
    print(json.dumps(result, indent=2, default=str))


def cmd_run(agent, args):
    if not args.design or not args.gcode:
        print("Error: --design and --gcode required for full run")
        sys.exit(1)

    result = agent.run_full_production(
        product_id=args.product,
        sku=args.sku,
        design_file=args.design,
        gcode_file=args.gcode,
        quantity=args.quantity,
        edition_start=args.edition_start,
        edition_size=args.edition_size,
        creation_fee=args.fee,
        printer_id=args.printer,
        auto_certify=args.auto_certify,
    )
    print(json.dumps(result, indent=2, default=str))


def cmd_hash(agent, args):
    h = MakerAgent.hash_file(args.file)
    print(f"SHA-256: {h}")
    print(f"File:    {args.file}")


def main():
    parser = argparse.ArgumentParser(
        prog='maker_agent',
        description='Thronos Maker Agent — 3D print production manager')

    parser.add_argument('--config', '-c', help='Config file path')
    parser.add_argument('--node', '-n', help='Thronos node URL')
    parser.add_argument('--key', '-k', help='Private key (hex)')
    parser.add_argument('--key-file', '-K', help='Private key file')
    parser.add_argument('--tenant', '-t', help='Tenant ID')
    parser.add_argument('--printer', '-p', help='Printer ID')
    parser.add_argument('--verbose', '-v', action='store_true')

    sub = parser.add_subparsers(dest='command')

    sub.add_parser('info', help='Show wallet info')
    sub.add_parser('approve', help='Approve self as creator')

    p_batch = sub.add_parser('batch', help='Create production batch')
    p_batch.add_argument('--product', required=True)
    p_batch.add_argument('--sku', required=True)
    p_batch.add_argument('--design', required=True, help='3MF file path')
    p_batch.add_argument('--gcode', help='Gcode file (auto-upload to all jobs)')
    p_batch.add_argument('--quantity', type=int, default=1)
    p_batch.add_argument('--edition-start', type=int, default=1)
    p_batch.add_argument('--edition-size', type=int, default=100)
    p_batch.add_argument('--fee', type=float, default=0.0, help='Creation fee (THR)')
    p_batch.add_argument('--batch-id', help='Custom batch ID')

    p_gc = sub.add_parser('gcode', help='Upload gcode hash for job')
    p_gc.add_argument('job_id')
    p_gc.add_argument('file', help='Gcode file path')

    p_start = sub.add_parser('start', help='Start print job')
    p_start.add_argument('job_id')
    p_start.add_argument('--printer', '-p')

    p_done = sub.add_parser('complete', help='Complete print job')
    p_done.add_argument('job_id')

    p_fail = sub.add_parser('fail', help='Fail print job')
    p_fail.add_argument('job_id')
    p_fail.add_argument('--reason', '-r', default='')

    p_cert = sub.add_parser('certify', help='Sign & certify job (mint NFT)')
    p_cert.add_argument('job_id')

    p_stat = sub.add_parser('status', help='Get job production status')
    p_stat.add_argument('job_id')

    p_jobs = sub.add_parser('jobs', help='List jobs')
    p_jobs.add_argument('--batch-id', '-b')
    p_jobs.add_argument('--status', '-s')

    p_run = sub.add_parser('run', help='Full production run')
    p_run.add_argument('--product', required=True)
    p_run.add_argument('--sku', required=True)
    p_run.add_argument('--design', required=True)
    p_run.add_argument('--gcode', required=True)
    p_run.add_argument('--quantity', type=int, default=1)
    p_run.add_argument('--edition-start', type=int, default=1)
    p_run.add_argument('--edition-size', type=int, default=100)
    p_run.add_argument('--fee', type=float, default=0.0)
    p_run.add_argument('--printer', '-p')
    p_run.add_argument('--auto-certify', action='store_true',
                       help='Auto-complete and certify (testing mode)')

    p_hash = sub.add_parser('hash', help='Hash a file (SHA-256)')
    p_hash.add_argument('file')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == 'hash':
        h = MakerAgent.hash_file(args.file)
        print(f"SHA-256: {h}")
        print(f"File:    {args.file}")
        return

    agent = _get_agent(args)
    commands = {
        'info': cmd_info,
        'approve': cmd_approve,
        'batch': cmd_batch,
        'gcode': cmd_gcode,
        'start': cmd_start,
        'complete': cmd_complete,
        'fail': cmd_fail,
        'certify': cmd_certify,
        'status': cmd_status,
        'jobs': cmd_jobs,
        'run': cmd_run,
    }
    commands[args.command](agent, args)


if __name__ == '__main__':
    main()
