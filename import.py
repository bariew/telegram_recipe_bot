import mysql.connector
import json

from recipe_bot.local import local_params


def main():
    mydb = mysql.connector.connect(
        host="localhost",
        user=local_params['database_username'],
        password=local_params['database_password'],
        database="food"
    )
    mycursor = mydb.cursor()
    sql = "INSERT INTO recipe (name, ingredients, url, image, cookTime, prepTime, description) " \
          "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    values = []
    for line in open('/var/www/telegram/20170107-061401-recipeitems.json', 'r'):
        data = json.loads(line)
        for i in ["name", "ingredients", "url", "image", "cookTime", "prepTime", "description"]:
            if i not in data.keys():
                data[i] = ''
        values.append((data["name"], data["ingredients"]+"\n", data["url"], data["image"], data["cookTime"],
                       data["prepTime"], data["description"]))
        if len(values) == 1000:
            mycursor.executemany(sql, values)
            mydb.commit()
            values = []
    print("OK")


if __name__ == '__main__':
    main()

