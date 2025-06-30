from idlelib.configdialog import changes
import asyncio

from bsv import (
    Transaction,
    TransactionInput,
    TransactionOutput,
    PrivateKey,
    P2PKH,
    BroadcastResponse,
    ARC
)

"""
Simple example of synchronous ARC broadcasting and status checking.
"""
# ARC_URL='https://api.taal.com/arc'

async def main():
# def main():

    # Setup ARC broadcaster
    arc = ARC('https://api.taal.com/arc', "mainnet_2e3a7d0f845a5049b35e9dde98fc4271")

    # Create a simple transaction
    private_key = PrivateKey("Kzpr5a6TmrXNw2NxSzt6GUonvcP8ABtfU17bdGEjxCufyxGMo9xV")
    public_key = private_key.public_key()

    source_tx = Transaction.from_hex(
        "01000000016ccb286539ac3ec33cb2ac0f1be2645a743395b8fe68bebc0b5202c1ce220084000000006b483045022100e5a0b5e592e1a38b0a92071c0da4e4da9658bd6808e0d2edb5282cb562bfe48b022072d492df5b1a903e082113a5b39fcc2504f446ac866ceb93fa62b5f0c60bf377412103e23c79a29b5e5f20127ec2286413510662d0e6befa29d669a623035122753d3affffffff013e000000000000001976a914047f8e69ca8eadec1b327d1b232cdaaffa200d1688ac00000000"
    )

    tx = Transaction(
        [
            TransactionInput(
                source_transaction=source_tx,
                source_txid=source_tx.txid(),
                source_output_index=0,
                unlocking_script_template=P2PKH().unlock(private_key),
            )
        ],
        [
            TransactionOutput(
                locking_script=P2PKH().lock("1QnWY1CWbWGeqobBBoxdZZ3DDeWUC2VLn"),
                change=True
            )
        ],
    )

    tx.fee()
    tx.sign()
    txid = tx.txid()
    txhex = tx.hex()
    print(f"Transaction ID: {txid}")
    print(f"Transaction hex: {txhex}")
    # Broadcast transaction
    result = await arc.broadcast(tx)
    # result = arc.sync_broadcast(tx)

    if isinstance(result, BroadcastResponse):
        print(f"Broadcast successful: {result.txid}")

        # Check status
        status = arc.check_transaction_status(result.txid)
        print(f"Status: {status.get('txStatus', 'Unknown')}")

        # Categorize status
        category = arc.categorize_transaction_status(status)
        print(f"Category: {category.get('status_category')}")

    else:
        print(f"Broadcast failed: {result.description}")


if __name__ == "__main__":
    # main()
    asyncio.run(main())
