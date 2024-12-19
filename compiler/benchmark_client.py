import socket, queue, subprocess

serverIP = '127.0.0.1'
serverPort = 12345


def startClientSocket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((serverIP, serverPort))
    print(f'Connected to {serverIP}:{serverPort}')
    return sock


def commandLoop():
    cmdBuf = queue.Queue()
    msg = ''
    while True:
        try:
            if not cmdBuf.empty():
                cmd = cmdBuf.get().split(' ')
                fst = cmd[0]
                if fst == 'save':
                    loc = cmd[1]
                    data = ' '.join(cmd[2:])
                    with open(loc, 'w') as f:
                        f.write(data)
                        f.close()
                    print('Received benchmark code file ' + loc)
                elif fst == 'execute':
                    print('Starting test execution "{}"'.format(' '.join(cmd[1:])))
                    p = subprocess.Popen(cmd[1:], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,)
                    try:
                        stdout, stderr = p.communicate(timeout=1000)
                    except TimeoutError:
                        print('Timed out')
                        s.send('error'.encode())
                    assert p.returncode == 0, stderr
                    print(stdout)
                    print('Test execution complete')
                elif fst == 'quit':
                    print('Exiting...')
                    s.send(fst.encode())
                    s.close()
                    return
                s.send(fst.encode())
            msg += s.recv(1024).decode()
            while chr(3) in msg:
                i = msg.index(chr(3))
                cmdBuf.put(msg[:i])
                msg = '' if i == len(msg)-1 else msg[i+1:]
        except:
            print('Unknown error encountered')
            s.send('error'.encode())


s = startClientSocket()
commandLoop()
