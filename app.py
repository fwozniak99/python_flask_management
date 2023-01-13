from flask import Flask, jsonify, request
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()
app = Flask(__name__)

uri = os.getenv("URI")
user = os.getenv("USERNAME")
password = os.getenv("PASSWORD")
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "s3cr3t"), database="neo4j")


def get_employees(tx, sorter, search, filterType):
    query = 'MATCH (n:Employee) RETURN n'
    if search and filterType is not None:
        if filterType == 'name':
            query = "MATCH (n:Employee) WHERE toLower(n.name) CONTAINS toLower($search) RETURN n"
        elif filterType == 'surname':
            query = "MATCH (n:Employee) WHERE toLower(n.surname) CONTAINS toLower($search) RETURN n"
        elif filterType == 'position':
            query = "MATCH (n:Employee) WHERE toLower(n.position) CONTAINS toLower($search) RETURN n"

    results = tx.run(query, search=search).data()
    # print(results)
    results = [result['n'] for result in results]

    if sorter is not None:
        if sorter == 'name':
            results = sorted(results, key=lambda result: result['name'])
        elif sorter == 'surname':
            results = sorted(results, key=lambda result: result['surname'])
        elif sorter == 'age':
            results = sorted(results, key=lambda result: result['age'])
        elif sorter == 'position':
            results = sorted(results, key=lambda result: result['position'])

    # employees = [{"name": result['n']['name'], "surname": result['n']['surname'], "age": result['n']['age'],
    #              "position": result['n']['position']} for result in results]
    return results


# get employees and filter&sort
@app.route('/employees', methods=['GET'])
def get_employees_route():
    args = request.args
    search = args.get("search")
    filterType = args.get("filterType")
    sorter = args.get("sorter")

    with driver.session() as session:
        employees = session.read_transaction(get_employees, sorter, search, filterType)
    response = {'employees': employees}
    return jsonify(response)


def add_employee(tx, name, surname, age, position, department):
    query = "MATCH (n:Employee) WHERE n.name=$name AND n.surname=$surname RETURN n"
    if tx.run(query, name=name, surname=surname).data():
        return 'Person with this name and surname already exists'
    else:
        query = "CREATE (n:Employee {name: $name, surname: $surname, age: $age, position: $position})"
        queryRelationship = "MATCH (n:Employee),(d:Department) WHERE n.name = $name AND n.surname = $surname AND " \
                            "d.name = $department CREATE (n)-[r:WORKS_IN]->(d) RETURN r "
        tx.run(query, name=name, surname=surname, age=age, position=position)
        tx.run(queryRelationship, name=name, surname=surname, age=age, department=department)


# add an employee
@app.route('/employees', methods=['POST'])
def add_employee_route():
    name = request.json['name']
    surname = request.json['surname']
    age = request.json['age']
    position = request.json['position']
    department = request.json['department']

    if name == '' or surname == '' or age == '' or position == '' or department == '':
        return 'Must include name, surname, age, position and department'

    with driver.session() as session:
        session.write_transaction(add_employee, name, surname, age, position, department)

    response = {'status': 'success'}
    return jsonify(response)


def delete_employee(tx, employeeID):
    query = "MATCH (n:Employee)-[r]-(d:Department) WHERE ID(n)=$employeeID RETURN n, d, r"
    result = tx.run(query, employeeID=employeeID).data()

    if not result:
        return None
    else:
        query = "MATCH (n:Employee) WHERE ID(n)=$employeeID DETACH DELETE n"
        tx.run(query, employeeID=employeeID)

        if "MANAGES" in result[0]["r"]:
            query = "MATCH (d:Department) WHERE d.name=$result[0]['d']['name'] DETACH DELETE d"
            tx.run(query, result=result)

        return {'id': employeeID}


# delete an employee
@app.route('/employees/<int:employeeID>', methods=['DELETE'])
def delete_employee_route(employeeID):
    with driver.session() as session:
        employee = session.write_transaction(delete_employee, employeeID)

    if not employee:
        response = {'message': 'Employee not found'}
        return jsonify(response), 404
    else:
        response = {'status': 'success'}
        return jsonify(response)


def get_departments(tx, sorter, search):
    query = 'MATCH (d:Department) RETURN d'
    if search is not None:
        query = "MATCH (d:Department) WHERE toLower(d.name) CONTAINS toLower($search) RETURN d"

    results = tx.run(query, search=search).data()

    results = [result['d'] for result in results]

    if sorter is not None:
        if sorter == 'name':
            results = sorted(results, key=lambda result: result['name'])

    return results


# get departments
@app.route('/departments', methods=['GET'])
def get_departments_route():
    args = request.args
    search = args.get("search")
    sorter = args.get("sorter")

    with driver.session() as session:
        departments = session.read_transaction(get_departments, sorter, search)
    response = {'departments': departments}
    return jsonify(response)


def update_employee(tx, employeeID, name, surname, age, position, department):
    query = "MATCH (n:Employee)-[r]-(d:Department) WHERE ID(n)=$employeeID RETURN n,d,r"
    result = tx.run(query, employeeID=employeeID).data()

    if not result:
        return None
    else:
        query = "MATCH (n:Employee) WHERE ID(n)=$employeeID SET n.name=$name, n.surname=$surname, n.age=$age, " \
                "n.position=$position"
        tx.run(query, employeeID=employeeID, name=name, surname=surname, age=age, position=position)
        query_relationship_delete = "MATCH (n:Employee )-[r:WORKS_IN]->(:Department) WHERE ID(n)=$employeeID DELETE r"
        tx.run(query_relationship_delete, employeeID=employeeID)
        query_relationship_create = "MATCH (n:Employee),(d:Department) WHERE ID(n)=$employeeID AND d.name=$department " \
                                    "CREATE (n)-[r:WORKS_IN]->(d) RETURN r "
        tx.run(query_relationship_create, employeeID=employeeID, department=department)
        return {'name': name, 'surname': surname, 'age': age, 'position': position, 'department': department}


# update an employee
@app.route('/employees/<int:employeeID>', methods=['PUT'])
def update_employee_route(employeeID):
    name = request.json['name']
    surname = request.json['surname']
    age = request.json['age']
    department = request.json['department']
    position = request.json['position']

    with driver.session() as session:
        employee = session.write_transaction(
            update_employee, employeeID, name, surname, age, position, department)

    if not employee:
        response = {'message': 'Employee not found'}
        return jsonify(response), 404
    else:
        response = {'status': 'success'}
        return jsonify(response)


def get_department_employees(tx, department):
    query = "MATCH (n:Employee)-[:WORKS_IN]-(d:Department) WHERE d.name=$department RETURN n"

    results = tx.run(query, department=department).data()
    employees = [{'name': result['n']['name'], 'surname': result['n']['surname'], 'age': result['n']['age'],
                  'position': result['n']['position']} for
                 result in results]
    return employees


# return all employees from a department
@app.route('/departments/<string:department>/employees', methods=['GET'])
def get_department_employees_route(department):
    with driver.session() as session:
        employees = session.execute_read(get_department_employees, department)

    response = {'employees': employees}
    return jsonify(response)


def get_employees_department(tx, employeeID):
    query = "MATCH (n:Employee)-[r1:WORKS_IN]->(d:Department)<-[r2:MANAGES]-(n2:Employee) WHERE ID(n)=$employeeID " \
            "RETURN d.name as department, n2.name as manager "
    result = tx.run(query, employeeID=employeeID).data()

    departments = [{'Department name': result[0]['department'], 'Manager name': result[0]['manager']}]
    return departments


# get department info for an employee
@app.route('/employees/<int:employeeID>/department', methods=['GET'])
def get_employees_department_route(employeeID):

    with driver.session() as session:
        departments = session.read_transaction(get_employees_department, employeeID)

    response = {'department': departments}
    return jsonify(response)


if __name__ == '__main__':
    app.run()
