from app.db import SessionLocal
from sqlalchemy import text

NEW_TOKEN = "sl.u.AGYcP3HJTqR3Uo6DWlZ1-8NouqSu72lcsl-OpyblCwdedJs35EHtd1VYfv4ZluRdPfYUdwVYIgxIEwI5AhctCilzZkCPg6lBQKnNfmMbl8q0rBPYlJ1vwulTt8khRQYnrGgDwFNVEGsN2GzZnYeEM43imyp1Iuyrnmktm3vIKUcnd8a-AryLpQBcjL51ycTY8gS345DnBJ8RTZaWZiEt9kFXvdNuvflQZAGsBWZsVfo-UAMdrXEprAAlkbcdIQs9b5zb6ojkrxZ5r37GMt8ZakWYskqNKjnXh_9IAUbSwp9ectFAEa8UI-TeRSuOYsezuDXooVOuU-ljqVJi4cw4lipcPLqTEhXdsadtvX6vtqGLHOPz_hxKESw8pesNO-4_2H4U-w_ecRTXJ2toI9qY6t78pmEhrTeDzi_wb9qGlPwwss8EF3HxO0CfQX23kbE5374PTnlJ4yowHMA_11efFPL0lywzKYoqkhpxInNOK-inZRSKBZhjcvVldTcz3uHCAGQ3C3_6lyx7IN7cEWatUU3bSFL1I6PL6gaeGLM5anYQyzOBLMvNlnlL0UOtKDH9nQ-T68xLRjiSA1R24ZGekCocI7iYHrH-ruzAcit9JJhkW9zEstwAYaOGSQPsBBv8rzuMIoNnMNsfuHWFRf9QCTr1CL3GgNSoeTDIWWcQAoiW1i--gAkqqxDT6FbEhiKckJDNTt-doZcVbyysCcqQfZlUfz7aDtSl8XLSCXwBxGFFpZB5FUYCsUf-6qd8cAQfdCUH-drDo_VVKqaEq4pt0pyZkYW16CwQZ4CdH3y7l1QEe1GbcJsIXPdoA1Y3zxeBhcmbSHQPHWNUpf6RG72I65DKUxw5G3peU2YgfKTzFeYDXeIl20fzfPNN86FCpW_srptqsRxLtKDV2mO0EeR6QBWrbLh_5d4kcS0X2jD4M1ApQKQaWCm04ab2t7W5YX9F52vyeFIgBHUv7yqG9_e8K-ZubU3K9Ea-bq8kUJSGtVEsLikZ8o3teim4-6t9mp11dk6g7WVJP-MXY1pmL9UAT97iijDvdcOiL6EVRDR_XVx5d3-fdZ_xebSewMWpkJtsGbTDMeAP2bcxE8QHJusKznBiipio-pBNFA_S0zuT37r4a20ToKgyP8gH7FKkxGnjElZ9eD-YA3CqNfWlQIZwJq3AEZ-puVrw61XJ-NyDbde04S1IOTwr6AnpG7pHR0F6UKAtJ_5yqicBFONMODhA3ApEQWOFWU74kclPrFbFUzEbaIh3AcnGNrNcUeOAkslptbm-LYd_Qqw99JUX0IKyTIp0OShZL8d62QTnokBHW7Ff8A"

db = SessionLocal()
try:
    result = db.execute(
        text('UPDATE "T_外部ストレージ連携" SET access_token = :token WHERE provider = :provider'),
        {'token': NEW_TOKEN, 'provider': 'dropbox'}
    )
    db.commit()
    print(f"Updated {result.rowcount} rows")
    
    # 確認
    rows = db.execute(text('SELECT provider, LEFT(access_token, 20) FROM "T_外部ストレージ連携"')).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
finally:
    db.close()
