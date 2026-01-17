import asyncio
import zmq.asyncio
import json

async def test_zmq():
    print("Starting ZMQ Test...")
    ctx = zmq.asyncio.Context()

    # Router
    router = ctx.socket(zmq.ROUTER)
    router.bind("tcp://127.0.0.1:5555")
    print("Router Bound")

    # Dealer
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect("tcp://127.0.0.1:5555")
    print("Dealer Connected")

    # Send
    msg = {"hello": "world"}
    await dealer.send_json(msg)
    print("Sent Message")

    # Receive
    frames = await router.recv_multipart()
    print(f"Received Frames: {len(frames)}")

    identity = frames[0]
    data = json.loads(frames[-1])
    print(f"Data: {data}")

    router.close()
    dealer.close()
    ctx.term()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(test_zmq())
