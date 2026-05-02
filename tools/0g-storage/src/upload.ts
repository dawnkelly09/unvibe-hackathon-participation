/**
 * 0G Storage uploader for the Unvibe Hackathons judging pipeline.
 *
 * Usage:
 *   npx tsx src/upload.ts <file-path>
 *
 * On success, prints a single JSON object to stdout:
 *   {
 *     "rootHash":   "0x...",
 *     "txHash":     "0x...",
 *     "network":    "galileo",
 *     "filePath":   "<absolute-path>",
 *     "fileSize":   <bytes>,
 *     "uploadedAt": "<iso-8601-utc>"
 *   }
 *
 * Progress messages and errors go to stderr so stdout stays machine-parseable.
 *
 * Adapted from 0gfoundation/0g-agent-skills examples/file-vault/src/upload.ts.
 */

import { ZgFile, Indexer } from '@0gfoundation/0g-storage-ts-sdk';
import { ethers } from 'ethers';
import * as fs from 'fs';
import * as path from 'path';
import 'dotenv/config';

interface UploadResult {
    rootHash: string;
    txHash: string | null;
    network: string;
    filePath: string;
    fileSize: number;
    uploadedAt: string;
}

async function upload(filePath: string): Promise<UploadResult> {
    // Validate environment
    if (!process.env.PRIVATE_KEY) throw new Error('PRIVATE_KEY not set in .env');
    if (!process.env.RPC_URL) throw new Error('RPC_URL not set in .env');
    if (!process.env.STORAGE_INDEXER) throw new Error('STORAGE_INDEXER not set in .env');

    // Validate file
    if (!fs.existsSync(filePath)) throw new Error(`File not found: ${filePath}`);
    const stats = fs.statSync(filePath);
    if (stats.size === 0) throw new Error('Cannot upload empty file');

    const absPath = path.resolve(filePath);
    console.error(`Uploading ${absPath} (${stats.size} bytes)...`);

    // Initialize provider, wallet, indexer
    const provider = new ethers.JsonRpcProvider(process.env.RPC_URL);
    const wallet = new ethers.Wallet(process.env.PRIVATE_KEY, provider);

    // Sanity-check wallet balance — empty wallet won't be able to pay for upload tx
    const balance = await provider.getBalance(wallet.address);
    if (balance === 0n) {
        throw new Error(
            `Wallet ${wallet.address} has zero 0G balance. Fund it from the Galileo faucet.`,
        );
    }
    console.error(`Wallet ${wallet.address} balance: ${ethers.formatEther(balance)} OG`);

    const indexer = new Indexer(process.env.STORAGE_INDEXER);
    const file = await ZgFile.fromFilePath(absPath);

    try {
        console.error('Generating Merkle tree...');
        const [tree, treeErr] = await file.merkleTree();
        if (treeErr) throw new Error(`Merkle tree generation failed: ${treeErr}`);

        const rootHash = tree!.rootHash()!;
        console.error(`Root hash: ${rootHash}`);

        console.error('Uploading to 0G Storage (Galileo)...');
        const [tx, uploadErr] = await indexer.upload(file, process.env.RPC_URL, wallet as any);
        if (uploadErr) throw new Error(`Upload failed: ${uploadErr.message}`);

        // Single-file shape: { rootHash, txHash, txSeq }. Fragmented (>4GB) shape
        // returns plural arrays; our reports are well under that threshold.
        const txHash =
            tx && typeof tx === 'object' && 'txHash' in tx && typeof tx.txHash === 'string'
                ? tx.txHash
                : null;

        console.error(`Upload complete. Tx: ${txHash ?? '(not in response)'}`);

        return {
            rootHash,
            txHash,
            network: 'galileo',
            filePath: absPath,
            fileSize: stats.size,
            uploadedAt: new Date().toISOString(),
        };
    } finally {
        await file.close();
    }
}

// CLI entrypoint
const filePath = process.argv[2];
if (!filePath) {
    console.error('Usage: npx tsx src/upload.ts <file-path>');
    process.exit(1);
}

upload(filePath)
    .then((result) => {
        // Stdout gets ONLY the JSON result, so callers can parse it directly.
        process.stdout.write(JSON.stringify(result, null, 2) + '\n');
    })
    .catch((err) => {
        console.error(`\nError: ${err.message}`);
        process.exit(1);
    });