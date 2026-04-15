from ftplib import FTP

ftp = FTP('test.rebex.net')
ftp.login('demo', 'password')

print("Current directory listing:")
ftp.retrlines('LIST')

# Try downloading a known file
with open('readme.txt', 'wb') as f:
    ftp.retrbinary('RETR readme.txt', f.write)

ftp.quit()
print("File downloaded successfully!")
